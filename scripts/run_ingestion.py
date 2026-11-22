"""
CLI script to trigger a single ingestion run.

Meant to be called by an external scheduler (GitHub Actions, Render Cron Job,
system cron) when the web process may be asleep and cannot run APScheduler.

Usage:
    python -m scripts.run_ingestion                    # uses .env settings
    python -m scripts.run_ingestion --dry-run          # zero network traffic
    python -m scripts.run_ingestion --source all       # PVP + enrichment
    python -m scripts.run_ingestion --force            # ignore a previous 403 stop

Exit codes: 0 = completed / dry_run, 1 = failed or errors.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from app.db.database import AsyncSessionFactory, engine
from app.ingestion.ingestion_service import IngestionService


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Killer Aste ingestion pass.")
    parser.add_argument("--source", choices=["pvp", "enrichment", "all"], default="pvp")
    parser.add_argument("--dry-run", action="store_true", default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    log = structlog.get_logger(__name__)
    log.info("manual_ingestion.start", source=args.source, dry_run=args.dry_run, force=args.force)

    try:
        async with AsyncSessionFactory() as session:
            service = IngestionService(session, dry_run=args.dry_run)
            result = await service.run(source=args.source, force=args.force)
    finally:
        await engine.dispose()

    log.info("manual_ingestion.done", **result)
    ok = result.get("status") in ("completed", "dry_run") and result.get("errors_count", 0) == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
