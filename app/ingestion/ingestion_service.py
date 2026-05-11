"""
Ingestion Service — orchestrates ingestion runs across multiple strategies.

Strategies
──────────
pvp         PVP list pages + per-auction detail enrichment (valore di stima,
            source URL, expert report). Both use the AntiBanHTTPClient.

enrichment  Public opportunity discovery — scrapes configured monitors
            (municipality portals, PNRR API, RSS feeds) and stores new
            opportunities in public_opportunities, linking them to properties.

all         Runs PVP then enrichment, sharing one AntiBanHTTPClient so
            rate-limiting and session rotation are applied uniformly.

Transaction safety
──────────────────
PVP record data (property + auction + analytics) is committed BEFORE the
enrichment correlation step. A failed enrichment (e.g. migration not yet
applied) never rolls back a successfully scraped record.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, date, timezone
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings, load_yaml_config
from app.core.enrichment_engine import EnrichmentEngine, OpportunityInput
from app.core.risk_engine import RiskEngine
from app.core.roi_engine import ROIEngine
from app.db.models import IngestionStatus
from app.db.repository import (
    AuctionRepository,
    EnrichmentSignalRepository,
    IngestionLogRepository,
    PropertyRepository,
    PublicOpportunityRepository,
    RiskFlagRepository,
    ValuationRepository,
)
from app.ingestion.cancellation import consume, is_cancel_requested
from app.ingestion.http_client import (
    AntiBanHTTPClient,
    AccessDenied,
    DailyCap,
    RateLimited,
)
from app.ingestion.parser import is_last_page, parse_api_response
from app.ingestion.pvp_detail import fetch_detail

log = structlog.get_logger(__name__)


class _CancelledByAdmin(Exception):
    pass


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()
        self._yaml_cfg = load_yaml_config()
        self._roi_engine = ROIEngine(self._yaml_cfg["roi"])
        self._risk_engine = RiskEngine(self._yaml_cfg["risk"])
        self._enrichment_engine = EnrichmentEngine(self._yaml_cfg.get("enrichment", {}))

        # Repositories
        self._props = PropertyRepository(session)
        self._auctions = AuctionRepository(session)
        self._valuations = ValuationRepository(session)
        self._flags = RiskFlagRepository(session)
        self._logs = IngestionLogRepository(session)
        self._opportunities = PublicOpportunityRepository(session)
        self._signals = EnrichmentSignalRepository(session)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, source: str = "pvp") -> dict:
        """
        Execute one ingestion run.

        source:
          "pvp"        → strategy 1+2: PVP list pages + per-auction detail pages
          "enrichment" → strategy 3:   public opportunity discovery
          "all"        → PVP then enrichment, sharing one HTTP client
        """
        run_pvp = source in ("pvp", "all")
        run_enrichment = source in ("enrichment", "all")

        run_id = str(uuid.uuid4())[:8]
        mode = (
            "dry_run" if self._settings.is_dry_run else self._settings.ingestion_mode
        )
        log.info("ingestion.start", run_id=run_id, source=source, mode=mode)

        log_entry = await self._logs.create(
            {"run_id": run_id, "source": source, "mode": mode}
        )
        await self._session.commit()

        stats = {
            "pages_fetched": 0,
            "records_found": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors_count": 0,
            "requests_made": 0,
            "properties_inserted": 0,
            "properties_updated": 0,
        }
        error_detail: Optional[str] = None
        final_status = IngestionStatus.COMPLETED
        next_cursor: int = 0

        run_timeout = self._yaml_cfg["ingestion"].get("max_run_seconds", 3600)

        try:
            async with AntiBanHTTPClient() as client:
                # ── Strategy 1+2: PVP list pages + detail pages ───────────────
                if run_pvp:
                    cursor_page = await self._logs.get_cursor("pvp")
                    log.info("ingestion.pvp_start", run_id=run_id, start_page=cursor_page)
                    next_cursor = await asyncio.wait_for(
                        self._run_pvp_strategy(
                            client, stats, start_page=cursor_page, run_id=run_id
                        ),
                        timeout=float(run_timeout),
                    )

                # ── Strategy 3: public enrichment discovery ───────────────────
                if run_enrichment and not self._settings.is_dry_run:
                    await self._run_enrichment_strategy(client, stats, run_id)

        except asyncio.TimeoutError:
            log.warning("ingestion.timeout", run_id=run_id, timeout_seconds=run_timeout)
            final_status = IngestionStatus.FAILED
            error_detail = f"Run exceeded maximum duration of {run_timeout // 60} minutes"
        except _CancelledByAdmin as exc:
            log.warning("ingestion.cancelled", run_id=run_id, error=str(exc))
            final_status = IngestionStatus.FAILED
            error_detail = str(exc)
        except DailyCap as exc:
            log.warning("ingestion.daily_cap", error=str(exc))
            final_status = IngestionStatus.COMPLETED
            error_detail = str(exc)
        except (RateLimited, AccessDenied) as exc:
            log.error("ingestion.ban_signal", error=str(exc))
            final_status = IngestionStatus.FAILED
            error_detail = str(exc)
            stats["errors_count"] += 1
        except Exception as exc:
            log.exception("ingestion.unexpected_error", error=str(exc))
            final_status = IngestionStatus.FAILED
            error_detail = str(exc)
            stats["errors_count"] += 1
        finally:
            if mode == "dry_run":
                final_status = IngestionStatus.DRY_RUN

            prop_stats = {
                "properties_inserted": stats.pop("properties_inserted"),
                "properties_updated": stats.pop("properties_updated"),
            }
            await self._logs.complete(
                log_entry.id,
                status=final_status,
                error_detail=error_detail,
                metadata={"next_page": next_cursor, **prop_stats},
                **stats,
            )
            await self._session.commit()

        log.info(
            "ingestion.complete",
            run_id=run_id,
            status=final_status.value,
            **stats,
        )
        return {"run_id": run_id, "status": final_status.value, **stats}

    # ── Strategy 1+2: PVP ────────────────────────────────────────────────────

    async def _run_pvp_strategy(
        self,
        client: AntiBanHTTPClient,
        stats: dict,
        start_page: int = 0,
        run_id: str = "",
    ) -> int:
        """
        Strategy 1: paginate PVP search results.
        Strategy 2: for each new auction, fetch the detail page (valore di stima,
                    source URL, expert report URL).

        Returns the next page cursor (0 = dataset end reached).
        """
        src_cfg = self._yaml_cfg["ingestion"]["sources"].get("pvp")
        if not src_cfg or not src_cfg.get("enabled", False):
            log.warning("ingestion.pvp_disabled")
            return 0

        base_url = src_cfg["base_url"]
        search_path = src_cfg["search_path"]
        max_pages = src_cfg.get("max_pages_per_run", 40)
        page_size = src_cfg.get("api_page_size", 20)
        api_body = src_cfg.get("api_body", {
            "tipoLotto": "IMMOBILI",
            "categoriaBene": [],
            "flagRicerca": 0,
            "coordIndirizzo": "",
            "raggioIndirizzo": "25",
        })

        url = f"{base_url}{search_path}"
        page = start_page
        end_page = start_page + max_pages

        while page < end_page:
            self._check_cancel(run_id, page)

            # Strategy 1: fetch one list page
            data, records = await self._fetch_list_page(
                client, url, api_body, page, page_size, stats
            )

            # Strategy 2: process each record (upsert + detail fetch + analytics)
            await self._process_pvp_page(client, records, stats, run_id, page)

            await self._logs.flush_stats(run_id, stats)
            await self._session.commit()

            if is_last_page(data) or not records:
                log.info("ingestion.pvp_dataset_complete", last_page=page)
                return 0

            if self._all_past(records):
                log.info("ingestion.pvp_reached_past_auctions", page=page)
                return 0

            page += 1

        log.info("ingestion.pvp_run_limit_reached", next_page=page)
        return page

    # ── Strategy 3: public enrichment discovery ───────────────────────────────

    async def _run_enrichment_strategy(
        self, client: AntiBanHTTPClient, stats: dict, run_id: str
    ) -> None:
        """
        Strategy 3: run configured municipality monitors to discover public
        opportunities, then correlate them with existing properties.

        Uses the same AntiBanHTTPClient as the PVP strategy so all HTTP
        calls count toward the same rate-limit and session rotation budget.
        """
        from app.ingestion.discovery.discovery_service import DiscoveryService

        log.info("ingestion.enrichment_strategy_start", run_id=run_id)
        try:
            svc = DiscoveryService(self._session)
            discovery_stats = await svc.run_with_client(client)
            stats["requests_made"] += discovery_stats.get("requests_made", 0)
            log.info(
                "ingestion.enrichment_strategy_done",
                run_id=run_id,
                **{k: v for k, v in discovery_stats.items() if k != "requests_made"},
            )
        except Exception as exc:
            log.warning("ingestion.enrichment_strategy_error", run_id=run_id, error=str(exc))

    # ── PVP helpers ───────────────────────────────────────────────────────────

    def _check_cancel(self, run_id: str, page: int) -> None:
        if run_id and is_cancel_requested(run_id):
            consume(run_id)
            raise _CancelledByAdmin(f"Cancelled by admin at page {page}")

    async def _fetch_list_page(
        self,
        client: AntiBanHTTPClient,
        url: str,
        api_body: dict,
        page: int,
        page_size: int,
        stats: dict,
    ) -> tuple[dict, list]:
        """Strategy 1: fetch one PVP search result page."""
        params = {
            "language": "it",
            "page": page,
            "size": page_size,
            "sort": ["dataOraVendita,desc", "citta,asc"],
        }
        log.info("ingestion.pvp_fetching_page", page=page, url=url)
        try:
            response = await client.post(url, json=api_body, params=params)
        except (RateLimited, AccessDenied):
            stats["requests_made"] += 1
            raise
        stats["requests_made"] += 1
        stats["pages_fetched"] += 1
        data = response.json()
        records = parse_api_response(data)
        stats["records_found"] += len(records)
        return data, records

    async def _process_pvp_page(
        self,
        client: AntiBanHTTPClient,
        records: list,
        stats: dict,
        run_id: str,
        page: int,
    ) -> None:
        for record in records:
            self._check_cancel(run_id, page)
            await self._process_pvp_record(client, record, stats)

    @staticmethod
    def _all_past(records: list) -> bool:
        today = date.today()
        return all(
            (r["auction_data"].get("auction_date") or datetime.min).date() < today
            for r in records
        )

    async def _process_pvp_record(
        self, client: AntiBanHTTPClient, record: dict, stats: dict
    ) -> None:
        """
        Process one PVP search result:
          1. Upsert property and auction
          2. Strategy 2: fetch detail page for new/incomplete auctions
          3. Run ROI + risk engines
          4. Commit — this is the transactional boundary
          5. Apply public enrichment correlation (best-effort, own commit)
        """
        prop_data = record["property_data"]
        auction_data = record["auction_data"]
        external_id = prop_data["external_id"]

        # ── Step 1-3: upsert + detail + analytics (one transaction) ──────────
        try:
            prop, prop_created = await self._props.upsert(prop_data)
            auction_data["property_id"] = prop.id

            auction, auction_created = await self._auctions.upsert(auction_data)

            # Strategy 2: detail page fetches valore di stima, source URL, etc.
            needs_detail = auction_created or not auction.source_url
            if needs_detail and not self._settings.is_dry_run:
                await self._fetch_pvp_detail(client, auction, prop, external_id, stats)

            if auction_created:
                stats["records_inserted"] += 1
            else:
                stats["records_updated"] += 1

            if prop_created:
                stats["properties_inserted"] += 1
            else:
                stats["properties_updated"] += 1

            await self._compute_analytics(auction, prop)
            await self._session.commit()  # ← commit core data before enrichment

        except Exception as exc:
            log.warning(
                "ingestion.pvp_record_error",
                external_id=external_id,
                error=str(exc),
            )
            await self._session.rollback()
            stats["errors_count"] += 1
            return  # do not attempt enrichment if core processing failed

        # ── Step 5: public enrichment correlation (separate transaction) ──────
        # This is completely decoupled: a failure here never affects the record
        # data committed above. If public_opportunities table doesn't exist yet,
        # the inner except catches it and we move on.
        try:
            await self._apply_enrichment_signals(prop)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            log.debug("ingestion.enrichment_skipped", property_id=str(prop.id), error=str(exc))

    # ── Strategy 2: PVP detail page ───────────────────────────────────────────

    async def _fetch_pvp_detail(
        self,
        client: AntiBanHTTPClient,
        auction,
        prop,
        external_id: str,
        stats: dict,
    ) -> None:
        """
        Strategy 2: fetch the PVP detail page.

        Enriches auction with: source_url, expert_report_url, deposit_required,
        auction_deadline.
        Enriches property with: market_value_estimate (valore di stima).
        """
        src_cfg = self._yaml_cfg["ingestion"]["sources"].get("pvp", {})
        base_url = src_cfg.get("base_url", "https://pvp.giustizia.it")
        detail_api_path = src_cfg.get(
            "detail_api_path", "/ric-496b258c-986a1b71/ric-ms/offerta/{id}"
        )
        detail_html_path = src_cfg.get("detail_html_path", "/pvp/it/detail_offerta.page")

        try:
            detail = await fetch_detail(
                client,
                base_url,
                external_id,
                detail_api_path=detail_api_path,
                detail_html_path=detail_html_path,
                stats=stats,
            )
        except Exception as exc:
            log.warning("ingestion.pvp_detail_error", external_id=external_id, error=str(exc))
            return

        if detail.get("source_url"):
            auction.source_url = detail["source_url"]
        if detail.get("expert_report_url"):
            auction.expert_report_url = detail["expert_report_url"]
        if detail.get("deposit_required") and not auction.deposit_required:
            auction.deposit_required = detail["deposit_required"]
        if detail.get("auction_deadline") and not auction.auction_deadline:
            auction.auction_deadline = detail["auction_deadline"]
        if detail.get("market_value") and not prop.market_value_estimate:
            prop.market_value_estimate = detail["market_value"]
            log.info(
                "ingestion.pvp_appraisal_stored",
                external_id=external_id,
                market_value=float(detail["market_value"]),
            )

    # ── Analytics ─────────────────────────────────────────────────────────────

    async def _compute_analytics(self, auction, prop) -> None:
        """Run ROI + risk engines and persist, replacing any stale valuation."""
        try:
            roi_result = self._roi_engine.calculate(
                base_price=float(auction.base_price or 0),
                area_sqm=float(prop.area_sqm or 0),
                market_value=float(prop.market_value_estimate or 0),
                property_type=prop.property_type.value if prop.property_type else "other",
            )
            existing = await self._valuations.get_by_auction(auction.id)
            if existing:
                await self._valuations.update(
                    existing.id, {"auction_id": auction.id, **roi_result.to_db_dict()}
                )
            else:
                await self._valuations.create(
                    {"auction_id": auction.id, **roi_result.to_db_dict()}
                )

            risk_result = self._risk_engine.evaluate(
                auction_data={
                    "base_price": float(auction.base_price or 0),
                    "minimum_bid": float(auction.minimum_bid or 0),
                    "court": auction.court,
                    "auction_type": auction.auction_type.value,
                },
                property_data={
                    "encumbrances": prop.encumbrances,
                    "province": prop.province,
                    "property_type": prop.property_type.value if prop.property_type else "other",
                    "condition_notes": prop.condition_notes,
                },
            )
            if risk_result.flags:
                await self._flags.delete_by_auction(auction.id)
                await self._flags.create_bulk(
                    [{"auction_id": auction.id, **f.to_db_dict()} for f in risk_result.flags]
                )
        except Exception as exc:
            log.warning("ingestion.analytics_error", auction_id=str(auction.id), error=str(exc))

    # ── Public enrichment correlation ─────────────────────────────────────────

    async def _apply_enrichment_signals(self, prop) -> None:
        """
        Correlate this property against already-discovered public opportunities
        and persist enrichment signals.

        This is a pure DB read+write operation — no HTTP calls. It runs AFTER the
        main PVP record has been committed, in its own transaction, so a failure
        (e.g. migration not yet applied) cannot corrupt the PVP record.
        """
        nearby = await self._opportunities.find_by_location(
            province=prop.province,
            city=prop.city,
            limit=20,
        )
        if not nearby:
            return

        opp_inputs = [
            OpportunityInput(
                id=str(o.id),
                opportunity_type=o.opportunity_type.value if o.opportunity_type else "altro",
                title=o.title,
                city=o.city,
                province=o.province,
                budget_amount=float(o.budget_amount) if o.budget_amount else None,
            )
            for o in nearby
        ]
        result = self._enrichment_engine.evaluate(
            opp_inputs,
            property_province=prop.province,
            property_city=prop.city,
        )

        if not result.is_significant():
            return

        for sig in result.signals:
            await self._signals.upsert_for_property(
                prop.id,
                sig["signal_type"],
                {k: v for k, v in sig.items() if k != "signal_type"},
            )
        for opp in nearby:
            await self._opportunities.link_to_property(
                property_id=prop.id,
                opportunity_id=opp.id,
            )
        log.info(
            "ingestion.enrichment_applied",
            property_id=str(prop.id),
            roi_uplift_pct=result.roi_market_value_uplift_pct,
            risk_reduction=result.risk_score_reduction,
            opportunity_count=result.opportunity_count,
        )
