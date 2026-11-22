# Killer Aste

Piattaforma di analisi delle aste immobiliari giudiziarie italiane. Legge i dati
pubblici del Portale Vendite Pubbliche (PVP), stima ROI e rischio di ogni lotto e
li presenta in una dashboard con filtri, mappa e preferiti.

- **Backend**: FastAPI, SQLAlchemy 2 (async) + PostgreSQL, Alembic, APScheduler
- **Frontend**: React 18 + Vite + Tailwind, login Google
- **Deploy di riferimento**: Render (backend), sito statico per il frontend

Architettura e roadmap dettagliate in [PLAN.md](PLAN.md).

## Avvio rapido (locale)

```bash
make setup                 # crea .env da .env.example e installa le dipendenze (dev incluse)
make dev-up                # Postgres + API in Docker, modalità dry_run (nessun traffico verso PVP)
make migrate               # applica le migrazioni Alembic
cd frontend && npm ci --legacy-peer-deps && npm run dev
```

Senza Docker: avvia un Postgres locale, poi `alembic upgrade head` e
`uvicorn app.api.main:app --reload`.

Per lavorare sul frontend senza backend: `VITE_SKIP_AUTH=true npm run dev`.

## Test

```bash
pytest -q                  # unit + integration (gli integration richiedono Postgres, altrimenti vengono saltati)
ruff check app tests scripts alembic
cd frontend && npx tsc --noEmit && npm run build
```

La CI (`.github/workflows/ci.yml`) esegue lint, migrazioni (up/down/up), test con
Postgres, typecheck/build del frontend e `npm audit`.

## Ingestion

Una run legge le pagine di ricerca PVP e il dettaglio di ogni nuovo lotto, poi
calcola ROI e rischio.

- **Modalità** (`INGESTION_MODE`): `safe` (default, 1 run/giorno, max 200
  richieste), `normal`, `dry_run` (risposte finte, zero rete).
- **Crawler educato**: User-Agent fisso e identificabile (`INGESTION_USER_AGENT`,
  mettici un contatto), pause tra le richieste, back-off sugli errori 5xx.
- **Tetto giornaliero persistente**: conteggiato su `ingestion_logs`, quindi
  regge anche ai riavvii.
- **Rifiuti rispettati**: un 429 ferma la run; un 403 ferma la run e blocca le
  successive finché un admin non ne lancia una con `force=true`
  (checkbox nel pannello admin, oppure `--force` da CLI).

Come lanciarla:

| Dove | Come |
|---|---|
| Pannello admin | Admin → Ingestion → “Avvia ingestion” |
| CLI | `python -m scripts.run_ingestion [--dry-run] [--source pvp\|public\|enrichment\|all] [--force]` |
| Schedulata, host sempre acceso | APScheduler interno (`SCHEDULER_ENABLED=true`) |
| Schedulata, Render free | GitHub Actions (`.github/workflows/ingestion.yml`), `SCHEDULER_ENABLED=false` |

Il piano free di Render va in sleep quando è inattivo, quindi lo scheduler
interno non partirebbe mai: per questo `render.yaml` lo disattiva e la run
giornaliera gira su GitHub Actions. Servono i secret `DATABASE_URL` e
`DATABASE_SYNC_URL` nel repository.

## Vendite di enti pubblici (alienazioni)

Oltre alle aste giudiziarie, la piattaforma raccoglie le vendite immobiliari di
Comuni, Province, ASL, Università, Agenzia del Demanio e altri enti
(`--source public`, oppure “Enti pubblici” nel pannello admin).

- **Gazzetta Ufficiale, 5ª Serie Speciale** (sezione “Aste immobiliari ed altre
  procedure ad evidenza pubblica”): fonte nazionale, attiva di default. Ogni
  run legge solo i numeri usciti dopo l'ultimo elaborato e non riscarica gli
  avvisi già salvati: dopo il primo giro (30 giorni, circa 40 richieste) costa
  pochi accessi al giorno.
- **Pagine degli enti** (`public_sales.html_sources` in `config/config.yaml`):
  qualunque pagina che elenca avvisi di vendita, con selettore CSS e filtro
  per parole chiave; i PDF vengono letti col parser PDF. Gli esempi
  (Agenzia del Demanio, un Comune) sono disattivati: vanno verificati i
  selettori sulla pagina reale prima di abilitarli.
- Ogni avviso viene diviso in lotti, con prezzo base, data dell'asta, scadenza
  offerte, comune/provincia (elenco ISTAT incluso), indirizzo e tipologia, e
  passa per gli stessi motori ROI e rischio delle aste PVP. Senza perizia il
  valore di mercato è assunto pari alla base d'asta (`market_value_factor: 1.0`),
  perché per gli enti la base è già la stima.
- Filtro geografico: `public_sales.provinces` / `regions`.
- In dashboard: filtro “Fonte” (Tribunali / Enti pubblici), badge “Ente
  pubblico” e link diretto all'avviso.

Gli avvisi sono testo libero scritto da migliaia di uffici diversi: l'estrazione
è best-effort e un campo non riconosciuto resta vuoto. Prima di partecipare
leggi sempre il bando completo.

## Modello ROI (`standard_v2`)

Oltre a prezzo, imposte, compensi e ristrutturazione, il modello include:
imposta di registro minima (1.000 €), arretrati condominiali che passano
all'acquirente (anno in corso e precedente), costi di mantenimento durante i
tempi di liberazione e rivendita, costi di vendita (agenzia + IVA) e imposta
sulla plusvalenza in caso di rivendita entro 5 anni. Tutti i parametri sono in
`config/config.yaml` (sezione `roi`) e sono **stime**: servono a non
sovrastimare il ROI, non sostituiscono una perizia o un commercialista.

## Sicurezza

- Login con Google ID token verificato con PyJWT (RS256 fisso, audience,
  issuer, `email_verified`), chiavi Google in cache.
- Il JWT dell'app identifica solo l'utente: ruolo, limite preferiti e stato
  attivo vengono letti dal DB a ogni richiesta, quindi un cambio di ruolo o una
  disattivazione hanno effetto subito.
- Endpoint di ingestion solo per admin; limite dei preferiti applicato lato
  server.
- In produzione l'app non parte senza `SECRET_KEY` (≥ 32 caratteri) e
  `GOOGLE_CLIENT_ID`.
- Dietro un reverse proxy imposta `FORWARDED_ALLOW_IPS` sull'indirizzo del proxy
  (su Render `*`) per registrare l'IP reale nell'audit dei login.

## Variabili d'ambiente principali

Vedi [.env.example](.env.example). In produzione servono almeno: `APP_ENV=production`,
`SECRET_KEY`, `DATABASE_URL`, `DATABASE_SYNC_URL`, `GOOGLE_CLIENT_ID`, `FRONTEND_URL`.
