"""
Ingestion Service — orchestrates one complete ingestion run.

Flow
────
1. Check daily request cap and last successful run (incremental guard)
2. Open AntiBanHTTPClient
3. Paginate through search results
4. For each new/changed record:
   a. Upsert property
   b. Upsert auction
   c. Fetch detail page (if auction is new)
   d. Run ROI + Risk engines
5. Commit stats to ingestion_log
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timezone
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings, load_yaml_config
from app.core.risk_engine import RiskEngine
from app.core.roi_engine import ROIEngine
from app.db.models import IngestionStatus
from app.db.repository import (
    AuctionRepository,
    IngestionLogRepository,
    PropertyRepository,
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

        # Repositories
        self._props = PropertyRepository(session)
        self._auctions = AuctionRepository(session)
        self._valuations = ValuationRepository(session)
        self._flags = RiskFlagRepository(session)
        self._logs = IngestionLogRepository(session)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, source: str = "pvp") -> dict:
        """
        Execute one ingestion run for the given source.
        Returns a summary dict.
        """
        run_id = str(uuid.uuid4())[:8]
        mode = (
            "dry_run" if self._settings.is_dry_run else self._settings.ingestion_mode
        )
        log.info("ingestion.start", run_id=run_id, source=source, mode=mode)

        log_entry = await self._logs.create(
            {
                "run_id": run_id,
                "source": source,
                "mode": mode,
            }
        )
        await self._session.commit()

        stats = {
            "pages_fetched": 0,
            "records_found": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors_count": 0,
            "requests_made": 0,
        }
        error_detail: Optional[str] = None
        final_status = IngestionStatus.COMPLETED
        cursor_page = await self._logs.get_cursor(source)
        log.info("ingestion.cursor", run_id=run_id, start_page=cursor_page)
        next_cursor: int = 0

        try:
            async with AntiBanHTTPClient() as client:
                next_cursor = await self._paginate(client, source, stats, start_page=cursor_page, run_id=run_id)
        except _CancelledByAdmin as exc:
            log.warning("ingestion.cancelled", run_id=run_id, error=str(exc))
            final_status = IngestionStatus.FAILED
            error_detail = str(exc)
        except DailyCap as exc:
            log.warning("ingestion.daily_cap", error=str(exc))
            final_status = IngestionStatus.COMPLETED  # not a failure, just a limit
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

            await self._logs.complete(
                log_entry.id,
                status=final_status,
                error_detail=error_detail,
                metadata={"next_page": next_cursor},
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

    # ── Pagination ────────────────────────────────────────────────────────────

    async def _paginate(
        self, client: AntiBanHTTPClient, source: str, stats: dict, start_page: int = 0, run_id: str = ""
    ) -> int:
        """Paginate from start_page up to max_pages_per_run pages.

        Returns the next page cursor (0 when the dataset end was reached).
        """
        src_cfg = self._yaml_cfg["ingestion"]["sources"].get(source)
        if not src_cfg or not src_cfg.get("enabled", False):
            log.warning("ingestion.source_disabled", source=source)
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
            data, records = await self._fetch_page(client, url, api_body, page, page_size, stats)
            await self._process_page_records(client, records, stats, run_id, page)

            if is_last_page(data) or not records:
                log.info("ingestion.dataset_complete", last_page=page)
                return 0

            if self._all_past(records):
                log.info("ingestion.reached_past_auctions", page=page)
                return 0

            page += 1

        log.info("ingestion.run_limit_reached", next_page=page)
        return page  # resume here next run

    # ── Record processing ─────────────────────────────────────────────────────

    async def _process_record(
        self, client: AntiBanHTTPClient, record: dict, stats: dict
    ) -> None:
        prop_data = record["property_data"]
        auction_data = record["auction_data"]
        external_id = prop_data["external_id"]

        try:
            prop, _ = await self._props.upsert(prop_data)
            auction_data["property_id"] = prop.id

            auction, auction_created = await self._auctions.upsert(auction_data)

            # Fetch detail page for new auctions, or existing ones still missing source_url.
            # This populates the real expert appraisal value and participation link.
            needs_detail = auction_created or not auction.source_url
            if needs_detail and not self._settings.is_dry_run:
                await self._enrich_from_detail(client, auction, prop, external_id)

            if auction_created:
                stats["records_inserted"] += 1
            else:
                stats["records_updated"] += 1

            await self._compute_analytics(auction, prop)
            await self._session.commit()

        except Exception as exc:
            log.warning(
                "ingestion.record_error",
                external_id=external_id,
                error=str(exc),
            )
            await self._session.rollback()
            stats["errors_count"] += 1

    async def _enrich_from_detail(
        self, client: AntiBanHTTPClient, auction, prop, external_id: str
    ) -> None:
        """Fetch the PVP detail page and update auction + property in place."""
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
            )
        except Exception as exc:
            log.warning("ingestion.detail_fetch_error", external_id=external_id, error=str(exc))
            return

        # Persist detail fields directly onto the ORM objects (already in session)
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
                "ingestion.appraisal_stored",
                external_id=external_id,
                market_value=float(detail["market_value"]),
            )

    async def _compute_analytics(self, auction, prop) -> None:
        """Run ROI + risk engines and persist results, replacing any existing valuation."""
        try:
            # ROI — uses real market_value if available, else engine falls back to ×1.3
            roi_result = self._roi_engine.calculate(
                base_price=float(auction.base_price or 0),
                area_sqm=float(prop.area_sqm or 0),
                market_value=float(prop.market_value_estimate or 0),
                property_type=prop.property_type.value if prop.property_type else "other",
            )
            # Replace any stale valuation for this auction
            existing = await self._valuations.get_by_auction(auction.id)
            if existing:
                await self._valuations.update(
                    existing.id, {"auction_id": auction.id, **roi_result.to_db_dict()}
                )
            else:
                await self._valuations.create(
                    {"auction_id": auction.id, **roi_result.to_db_dict()}
                )

            # Risk
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
                    [
                        {"auction_id": auction.id, **f.to_db_dict()}
                        for f in risk_result.flags
                    ]
                )
        except Exception as exc:
            log.warning("ingestion.analytics_error", auction_id=str(auction.id), error=str(exc))
