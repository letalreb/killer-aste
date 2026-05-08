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
from datetime import datetime, timezone
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
from app.ingestion.http_client import (
    AntiBanHTTPClient,
    AccessDenied,
    DailyCap,
    RateLimited,
)
from app.ingestion.parser import is_last_page, parse_api_response

log = structlog.get_logger(__name__)


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
                next_cursor = await self._paginate(client, source, stats, start_page=cursor_page)
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
        self, client: AntiBanHTTPClient, source: str, stats: dict, start_page: int = 0
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
            params = {
                "language": "it",
                "page": page,
                "size": page_size,
                "sort": ["dataOraVendita,asc", "citta,asc"],
            }
            log.info("ingestion.fetching_page", page=page, url=url)
            response = await client.post(url, json=api_body, params=params)
            stats["requests_made"] += 1
            stats["pages_fetched"] += 1

            data = response.json()
            records = parse_api_response(data)
            stats["records_found"] += len(records)

            for record in records:
                await self._process_record(client, record, stats)

            if is_last_page(data) or not records:
                log.info("ingestion.dataset_complete", last_page=page)
                return 0  # reset cursor — next run starts from the beginning

            page += 1

        log.info("ingestion.run_limit_reached", next_page=page)
        return page  # resume here next run

    # ── Record processing ─────────────────────────────────────────────────────

    async def _process_record(
        self, _client: AntiBanHTTPClient, record: dict, stats: dict
    ) -> None:
        prop_data = record["property_data"]
        auction_data = record["auction_data"]
        external_id = prop_data["external_id"]

        try:
            prop, _ = await self._props.upsert(prop_data)
            auction_data["property_id"] = prop.id

            auction, auction_created = await self._auctions.upsert(auction_data)

            if auction_created:
                stats["records_inserted"] += 1
                await self._compute_analytics(auction, prop)
            else:
                stats["records_updated"] += 1

            await self._session.commit()

        except Exception as exc:
            log.warning(
                "ingestion.record_error",
                external_id=external_id,
                error=str(exc),
            )
            await self._session.rollback()
            stats["errors_count"] += 1

    async def _compute_analytics(self, auction, prop) -> None:
        """Run ROI + risk engines and persist results."""
        try:
            # ROI
            roi_result = self._roi_engine.calculate(
                base_price=float(auction.base_price or 0),
                area_sqm=float(prop.area_sqm or 0),
                market_value=float(prop.market_value_estimate or 0),
                property_type=prop.property_type.value if prop.property_type else "other",
            )
            await self._valuations.create(
                {
                    "auction_id": auction.id,
                    **roi_result.to_db_dict(),
                }
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
                await self._flags.create_bulk(
                    [
                        {
                            "auction_id": auction.id,
                            **f.to_db_dict(),
                        }
                        for f in risk_result.flags
                    ]
                )
        except Exception as exc:
            log.warning("ingestion.analytics_error", auction_id=str(auction.id), error=str(exc))
