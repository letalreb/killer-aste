# Killer Aste — 14-Day Execution Plan & Architecture Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SOURCES                             │
│             Portale Vendite Pubbliche (pvp.giustizia.it)            │
└────────────────────────────┬────────────────────────────────────────┘
                             │  HTTPS (anti-ban client)
┌────────────────────────────▼────────────────────────────────────────┐
│                      INGESTION LAYER                                │
│  scheduler.py → ingestion_service.py → http_client.py              │
│                           ↓                                         │
│                        parser.py                                    │
│            (HTML → structured dicts, no DB calls)                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                     INTELLIGENCE LAYER                              │
│           roi_engine.py         risk_engine.py                      │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                      DATA LAYER (PostgreSQL)                        │
│  properties | auctions | valuations | risk_flags | ingestion_log    │
│                    (via repository.py)                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                       API LAYER (FastAPI)                           │
│   GET /api/v1/auctions        GET /api/v1/properties                │
│   POST /api/v1/analytics/roi  POST /trigger-ingestion               │
│   GET /health                 GET /metrics (Prometheus)             │
└─────────────────────────────────────────────────────────────────────┘

Supporting services: Redis (request-cap counters) · Prometheus + Grafana (metrics)
```

---

## Module Map

```
killer-aste-2/
├── app/
│   ├── config/
│   │   └── settings.py          ← Pydantic settings (env + .env file)
│   ├── ingestion/
│   │   ├── http_client.py       ← Anti-ban HTTP client (THE critical file)
│   │   ├── mock_responses.py    ← Dry-run HTML fixtures
│   │   ├── parser.py            ← HTML → plain dicts
│   │   ├── ingestion_service.py ← Orchestration (paginate → upsert → ROI/Risk)
│   │   └── scheduler.py         ← APScheduler (once/day safe, 2x/day normal)
│   ├── core/
│   │   ├── roi_engine.py        ← ROI calculator (pure Python, no I/O)
│   │   └── risk_engine.py       ← Risk scorer (weighted sub-scores + flags)
│   ├── db/
│   │   ├── models.py            ← SQLAlchemy 2.0 ORM (5 tables)
│   │   ├── database.py          ← Async engine + session factory
│   │   └── repository.py        ← Data access (upsert, queries)
│   └── api/
│       ├── main.py              ← FastAPI app (lifespan, CORS, metrics)
│       ├── schemas.py           ← Pydantic v2 response models
│       └── routes/
│           ├── auctions.py
│           ├── properties.py
│           └── analytics.py
├── config/
│   └── config.yaml              ← Domain knobs (delays, fees, risk weights)
├── alembic/                     ← DB migrations
├── tests/
│   ├── unit/                    ← ROI, risk, parser, HTTP client tests
│   └── integration/             ← Full pipeline test (needs PostgreSQL)
├── docker/
│   ├── Dockerfile               ← Multi-stage, non-root user
│   ├── docker-compose.yml       ← PostgreSQL + Redis + app
│   └── docker-compose.dev.yml   ← Hot-reload + dry_run override
└── scripts/
    └── run_ingestion.py         ← Manual trigger CLI
```

---

## Anti-Ban Strategy — Detailed Explanation

### Why previous attempts caused bans
Aggressive scrapers share these fingerprints:
- Fixed inter-request delays (looks robotic)
- High request velocity (>10 req/min)
- No cookie state (looks headless)
- Generic or missing User-Agent
- No session affinity

### How this system avoids bans

| Mechanism | Implementation | Effect |
|-----------|---------------|--------|
| Non-uniform delays | Beta(2,5) distribution → [1–8s] in safe mode | No detectable pattern |
| Think pauses | 20% chance of 15–45s pause | Mimics reading a page |
| Daily cap | Hard ceiling (80 req/day safe) | Well under server thresholds |
| Session cookies | `httpx.AsyncClient` with persistent cookies | Looks like a returning browser |
| UA rotation | 6 weighted Chrome/Firefox/Safari UAs | Avoids UA fingerprinting |
| Session rotation | New cookies every 40 requests or 45 min | Limits session duration fingerprint |
| 429 cooldown | 30 min freeze on rate-limit signal | Respectful back-off |
| 403 cooldown | 60 min freeze on access-denied | Avoid escalation to IP ban |
| Exponential back-off | 60s→120s→240s…→30min with ±25% jitter | Standard polite retry |
| Max concurrency: 1 | asyncio.Semaphore(1) in safe mode | Single sequential flow |
| Incremental runs | `last_successful` check → skip known records | Minimal repeated requests |
| Dry-run mode | Intercepts before I/O → fixture responses | Zero traffic during development |

---

## 14-Day Execution Plan

### DAY 1 — Project Foundation

**Goals:** Running local environment, DB accessible, linting passes.

**Tasks:**
1. `git init && git add . && git commit -m "initial scaffold"`
2. `cp .env.example .env` → fill in values
3. `pip install -r requirements.txt`
4. `docker compose -f docker/docker-compose.yml up -d db redis`
5. `alembic upgrade head`
6. `make test-unit` (parser, ROI, risk tests should pass without DB)

**Deliverables:**
- Working venv with all deps installed
- PostgreSQL + Redis running locally
- All 5 tables migrated
- Unit tests green

**Validation:**
```bash
psql $DATABASE_SYNC_URL -c "\dt"     # should list 5 tables
pytest tests/unit/ -v                # all green
```

---

### DAY 2 — Dry-Run Ingestion Verified

**Goals:** Ingestion pipeline runs end-to-end against mock responses.

**Tasks:**
1. Run `make dry-run`
2. Verify records in DB:
   ```sql
   SELECT * FROM properties LIMIT 5;
   SELECT * FROM auctions LIMIT 5;
   SELECT * FROM valuations LIMIT 5;
   SELECT * FROM ingestion_log;
   ```
3. Check risk_flags table populated
4. Tweak parser if mock HTML doesn't parse cleanly

**Deliverables:**
- Dry-run completes with status=dry_run in ingestion_log
- At least 3 properties and 3 auctions in DB
- Valuations computed for each auction

**Validation:**
```bash
make dry-run
psql $DATABASE_SYNC_URL -c "SELECT status, records_inserted FROM ingestion_log;"
```

---

### DAY 3 — API Layer Working

**Goals:** FastAPI serves auction and analytics endpoints.

**Tasks:**
1. Start API: `uvicorn app.api.main:app --reload`
2. Open `http://localhost:8000/docs`
3. Test endpoints manually:
   - `GET /api/v1/auctions`
   - `GET /api/v1/analytics/roi` with payload
   - `GET /health`
4. Fix any schema validation errors

**Deliverables:**
- All REST endpoints respond correctly
- `/docs` shows all routes
- `/health` returns 200

---

### DAY 4 — Real HTML Structure Analysis

**Goals:** Understand the real PVP HTML so parser selectors are correct.

**Tasks:**
1. Visit pvp.giustizia.it in browser → inspect source (DevTools)
2. Download one search-results page HTML manually (save-as)
3. Run parser against real HTML locally (no HTTP client):
   ```python
   from app.ingestion.parser import parse_search_results
   html = open("pvp_sample.html").read()
   records = parse_search_results(html)
   print(records)
   ```
4. Update parser selectors as needed
5. Save real HTML samples as fixtures in `tests/fixtures/`

**Deliverables:**
- `parser.py` selectors updated for real PVP structure
- Real HTML fixtures added to tests
- Unit tests updated to use real fixtures

**SAFETY NOTE:** Manual inspection only on Day 4 — zero automated requests.

---

### DAY 5 — First Live Test (SAFE MODE, 1 Page)

**Goals:** Make exactly 1 real request in safe mode. Verify it works.

**Tasks:**
1. Set `.env`: `INGESTION_MODE=safe`, `DRY_RUN=false`
2. Edit `config.yaml`: `max_pages_per_run: 1`
3. Run: `python -m scripts.run_ingestion`
4. Watch logs for: delay applied, UA used, response status
5. Check DB for real data
6. **Stop immediately** if 429 or 403 received

**Deliverables:**
- 1 real page fetched successfully
- Real properties/auctions in DB
- ingestion_log shows `requests_made: 1-3`

**Validation:**
```bash
tail -f logs/app.log  # watch for ban signals
psql $DATABASE_SYNC_URL -c "SELECT city, province, base_price FROM auctions LIMIT 5;"
```

---

### DAY 6 — 3-Page Live Test + Deduplication Verified

**Tasks:**
1. Bump `max_pages_per_run: 3`
2. Run twice → verify upsert is idempotent (no duplicates)
3. Check `records_inserted` vs `records_updated` in log
4. Verify incremental: second run has more `records_updated` than `records_inserted`

**Deliverables:**
- 3 pages ingested cleanly
- Zero duplicate records
- ingestion_log shows accurate counts

---

### DAY 7 — ROI Engine Tuning

**Goals:** Validate ROI calculations against real Italian market data.

**Tasks:**
1. Export auction data to spreadsheet
2. Compare ROI engine output vs. manual calculation for 5 auctions
3. Calibrate `renovation_cost_per_sqm` for regional markets
4. Add `prima_casa` tax scenario flag to API
5. Run full unit test suite

**Deliverables:**
- ROI engine validated against real data
- `config.yaml` calibrated per region (optional: per-province overrides)

---

### DAY 8 — Risk Engine Calibration

**Tasks:**
1. Review all risk flags generated for real ingested data
2. Calibrate province tier list (`_PROVINCE_TIER` in risk_engine.py)
3. Add missing province codes
4. Adjust `debt_burden` threshold (currently 40% discount → flag)
5. Manual review: do HIGH/CRITICAL flags correspond to genuinely risky lots?

**Deliverables:**
- Risk flags validated against real auction data
- Province tier list complete for Italy (≈100 provinces)

---

### DAY 9 — Data Enrichment (Optional)

**Optional tasks if time permits:**
- Add geocoding: call Nominatim API (free, OSM) to fill `latitude`/`longitude`
- Add OMI data lookup (Osservatorio Mercato Immobiliare) for market price estimates
- Add distance-from-city-center calculation

**Skip if behind schedule** — these are enhancements, not MVP blockers.

---

### DAY 10 — API Hardening

**Tasks:**
1. Add pagination metadata to list endpoints
2. Add `min_roi`, `max_base_price`, `auction_type` query filters to `/auctions`
3. Add sorting: `?sort=auction_date&order=asc`
4. Add OpenAPI descriptions to all endpoints
5. Test with 100+ records in DB (run dry-run to seed)

**Deliverables:**
- Fully documented, filterable API
- Load test: `wrk -t2 -c10 -d10s http://localhost:8000/api/v1/auctions`
- Response time < 200ms for list endpoint

---

### DAY 11 — Observability

**Tasks:**
1. Verify Prometheus metrics at `/metrics`
2. Set up Grafana locally: `docker run -p 3000:3000 grafana/grafana`
3. Import FastAPI dashboard (ID: 14283)
4. Create custom panel: "Daily request count" from ingestion_log
5. Add structured log fields: `run_id`, `source`, `mode` to all log statements
6. Test alert: force a 5xx and verify it shows in metrics

**Deliverables:**
- Grafana dashboard with 4 key panels:
  - Request rate (HTTP)
  - Error rate
  - Daily ingestion count
  - DB query latency

---

### DAY 12 — Full Test Suite

**Tasks:**
1. Run `make test` → target 80%+ coverage
2. Fix any failing tests
3. Add edge-case tests for parser (malformed HTML, missing fields)
4. Run integration tests against local Docker DB
5. Profile: find slowest queries, add missing indexes

**Deliverables:**
- All tests green
- Coverage ≥ 80%
- No N+1 queries (SQLAlchemy eager loading verified)

---

### DAY 13 — Performance & Security Hardening

**Tasks:**
1. Add request size limits to FastAPI
2. Verify no sensitive data in API responses (no raw court judge names exposed)
3. Add rate limiting to API with `slowapi`
4. Database connection pool tuning
5. Dockerfile security scan: `docker scout cves killer-aste-app`
6. Ensure non-root container user (already done in Dockerfile)

**Deliverables:**
- Security checklist complete
- API rate limited: 60 req/min per IP
- Docker image passes basic security scan

---

### DAY 14 — Production Deployment

**Tasks:**
1. Choose deployment target (see options below)
2. Set production environment variables
3. Build and push Docker image
4. Run migrations on production DB
5. Deploy with `INGESTION_MODE=safe` (PHASE 1)
6. Smoke test: `curl https://your-domain.com/health`
7. Set up uptime monitor (UptimeRobot — free)

**Deliverables:**
- Application live and healthy
- Ingestion scheduler running in SAFE MODE
- Monitoring dashboard accessible
- Rollback procedure documented

---

## Deployment Guide

### Option A: VPS (Hetzner CX21 — ~5€/month)

```bash
# On VPS
sudo apt install docker.io docker-compose-plugin

git clone https://github.com/you/killer-aste-2 /opt/killer-aste
cd /opt/killer-aste
cp .env.example .env
# Edit .env with production values

docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml exec app alembic upgrade head

# Nginx reverse proxy (optional, for HTTPS)
sudo apt install nginx certbot python3-certbot-nginx
```

### Option B: Fly.io (free tier → pay-as-you-go)

```bash
fly launch                    # creates fly.toml
fly secrets import < .env     # push env vars
fly postgres create           # managed PostgreSQL
fly deploy
```

### Option C: AWS ECS (Fargate)

Use the provided Dockerfile with:
- ECR for image registry
- RDS PostgreSQL for database
- ElastiCache for Redis
- ECS Fargate for zero-server deployment

---

## Rollout Strategy

### Phase 1 — Days 14–16: SAFE MODE (Initial)
```yaml
INGESTION_MODE: safe
max_pages_per_run: 3          # ≈ 15-20 records
daily_request_cap: 80
```
Monitor:
- HTTP error rate (target: 0%)
- 429/403 count in ingestion_log (target: 0)
- Response time (should be < 5s per page)

### Phase 2 — Days 17–21: Gradual Increase
After 5 clean days with zero ban signals:
```yaml
max_pages_per_run: 5 → 8 → 10  (increase by 2-3 every 2 days)
daily_request_cap: 80 → 150 → 250
```

### Phase 3 — Day 22+: NORMAL MODE
```yaml
INGESTION_MODE: normal
max_pages_per_run: 10
daily_request_cap: 400
```

### Rollback Triggers
Immediately revert to SAFE MODE if ANY of:
- HTTP 403 received
- HTTP 429 received more than 2x per run
- `errors_count > 10` in ingestion_log
- Source website changes structure (parser returns 0 records)

### Rollback Command
```bash
# On VPS
docker compose exec app sh -c "echo 'INGESTION_MODE=safe' >> /app/.env"
docker compose restart app
```

### Metrics to Monitor Daily
| Metric | Tool | Alert threshold |
|--------|------|-----------------|
| 429 rate | ingestion_log | Any occurrence |
| Error rate | ingestion_log | errors_count > 5 |
| Records/run | ingestion_log | < 1 (parser broken?) |
| API latency | Prometheus | p99 > 500ms |
| DB size | Grafana | > 1GB |

---

## Local Quick Start (5 commands)

```bash
# 1. Setup
cp .env.example .env && pip install -r requirements.txt

# 2. Start infrastructure
docker compose -f docker/docker-compose.yml up -d db redis

# 3. Migrate
alembic upgrade head

# 4. Dry-run ingestion (zero network)
make dry-run

# 5. Start API
uvicorn app.api.main:app --reload
# → Open http://localhost:8000/docs
```

---

## Key Design Decisions

**Why async SQLAlchemy 2.0?**
FastAPI is async-native. Sync DB calls block the event loop. `asyncpg` driver is
10–15x faster than `psycopg2` for async workloads.

**Why UUID primary keys?**
Prevents external ID enumeration via API. Also allows offline UUID generation
without round-trips to the DB.

**Why the repository pattern?**
Keeps business logic in service/engine layers, not scattered in route handlers.
Makes unit testing without DB trivial (inject a mock session).

**Why not Scrapy?**
Scrapy is designed for high-volume crawling. It would be harder to tune down
to the human-like pacing this use case requires. `httpx` + custom delays gives
precise, auditable control.

**Why YAML config + Pydantic settings?**
Two-tier config: operator-facing tuning knobs in YAML (delay, fees, risk weights),
infrastructure config in env vars (database URLs, secrets). Separates concerns cleanly.
