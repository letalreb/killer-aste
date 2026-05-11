"""
Discovery Service — orchestrates one complete discovery run.

Flow
────
1. Build monitors from config
2. For each monitor, discover raw opportunity data
3. Parse each raw item into a structured dict
4. Upsert into public_opportunities table
5. For each stored opportunity, link it to properties in the same city/province
6. Commit and return stats
"""
from __future__ import annotations

import uuid
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import load_yaml_config
from app.db.repository import EnrichmentSignalRepository, PublicOpportunityRepository
from app.ingestion.discovery.municipality_monitor import build_monitors
from app.ingestion.discovery.opportunity_parser import parse_opportunity
from app.ingestion.http_client import AntiBanHTTPClient

log = structlog.get_logger(__name__)


class DiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._yaml_cfg = load_yaml_config()
        self._enrichment_cfg = self._yaml_cfg.get("enrichment", {})
        self._opp_repo = PublicOpportunityRepository(session)
        self._signal_repo = EnrichmentSignalRepository(session)

    # ── Public entry points ───────────────────────────────────────────────────

    async def run(self, provinces: Optional[list[str]] = None) -> dict:
        """
        Execute a full discovery run with its own AntiBanHTTPClient.
        Use run_with_client() instead when the caller already has a client open
        (e.g. when invoked from IngestionService to share rate-limit budget).
        """
        async with AntiBanHTTPClient() as client:
            return await self.run_with_client(client, provinces=provinces)

    async def run_with_client(
        self,
        client: AntiBanHTTPClient,
        provinces: Optional[list[str]] = None,
    ) -> dict:
        """
        Execute a full discovery run using an already-open AntiBanHTTPClient.
        This allows the caller (IngestionService) to share rate-limiting state
        across PVP and enrichment HTTP calls.
        """
        stats = {
            "monitors_run": 0,
            "raw_items": 0,
            "opportunities_new": 0,
            "opportunities_updated": 0,
            "errors": 0,
            "requests_made": 0,
        }

        monitors = build_monitors(self._enrichment_cfg)
        if not monitors:
            log.info("discovery.no_monitors_configured")
            return stats

        for monitor in monitors:
            stats["monitors_run"] += 1
            try:
                raw_items = await monitor.discover(client, provinces=provinces)
                stats["raw_items"] += len(raw_items)
                log.info(
                    "discovery.monitor_done",
                    monitor=monitor.name,
                    items=len(raw_items),
                )
                for raw in raw_items:
                    await self._process_item(raw, monitor.name, stats)
            except Exception as exc:
                log.warning(
                    "discovery.monitor_error",
                    monitor=monitor.name,
                    error=str(exc),
                )
                stats["errors"] += 1

        await self._session.commit()
        log.info("discovery.complete", **stats)
        return stats

    async def link_property_opportunities(
        self,
        property_id: uuid.UUID,
        province: Optional[str],
        city: Optional[str],
    ) -> int:
        """
        Find active opportunities in the same city/province and link them to
        the given property.  Returns the number of new links created.
        """
        if not province and not city:
            return 0

        opportunities = await self._opp_repo.find_by_location(
            province=province, city=city
        )
        new_links = 0
        for opp in opportunities:
            relevance = _score_relevance(opp.opportunity_type.value if opp.opportunity_type else "altro")
            link = await self._opp_repo.link_to_property(
                property_id=property_id,
                opportunity_id=opp.id,
                relevance_score=relevance,
            )
            if link:
                new_links += 1

        return new_links

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _process_item(self, raw: dict, source: str, stats: dict) -> None:
        parsed = parse_opportunity(raw, source=source)
        if not parsed:
            return
        try:
            _, created = await self._opp_repo.upsert(parsed)
            if created:
                stats["opportunities_new"] += 1
            else:
                stats["opportunities_updated"] += 1
        except Exception as exc:
            log.warning("discovery.upsert_error", error=str(exc))
            stats["errors"] += 1


# ── Helpers ───────────────────────────────────────────────────────────────────

_RELEVANCE_SCORES: dict[str, float] = {
    "rigenerazione_urbana": 90.0,
    "pnrr_progetto": 85.0,
    "valorizzazione_immobiliare": 80.0,
    "piano_recupero": 75.0,
    "investimento_infrastrutturale": 70.0,
    "dismissione_pubblica": 60.0,
    "alienazione_pubblica": 55.0,
    "piano_urbanistico": 50.0,
    "altro": 30.0,
}


def _score_relevance(opportunity_type: str) -> float:
    return _RELEVANCE_SCORES.get(opportunity_type, 30.0)
