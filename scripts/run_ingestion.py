"""
CLI script to trigger a single ingestion run.

Usage:
    python -m scripts.run_ingestion                         # uses .env settings
    DRY_RUN=true python -m scripts.run_ingestion            # dry-run
    INGESTION_MODE=safe python -m scripts.run_ingestion     # safe mode
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from app.db.database import AsyncSessionFactory
from app.ingestion.ingestion_service import IngestionService


async def main() -> None:
    log = structlog.get_logger(__name__)
    log.info("manual_ingestion.start")

    async with AsyncSessionFactory() as session:
        service = IngestionService(session)
        result = await service.run(source="pvp")

    log.info("manual_ingestion.done", **result)
    if result.get("errors_count", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
