"""
APScheduler-based ingestion scheduler.

Schedules ingestion runs according to the active mode:
  safe     → once per day at a randomised time in off-peak hours
  normal   → twice per day
  dry_run  → every 5 minutes (for testing)

The scheduler is started by the FastAPI lifespan and stopped on shutdown.
"""
from __future__ import annotations

import random
from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config.settings import get_settings
from app.db.database import AsyncSessionFactory
from app.ingestion.ingestion_service import IngestionService

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_ingestion_job() -> None:
    log.info("scheduler.job_fired")
    async with AsyncSessionFactory() as session:
        service = IngestionService(session)
        result = await service.run(source="pvp")
    log.info("scheduler.job_done", **result)


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="Europe/Rome")
    mode = settings.ingestion_mode if not settings.is_dry_run else "dry_run"

    if mode == "dry_run":
        # Run every 5 minutes for local development / CI
        trigger = IntervalTrigger(minutes=5)
        log.info("scheduler.configured", mode="dry_run", interval_minutes=5)

    elif mode == "safe":
        # Once per day in off-peak hours (01:00 – 05:00), randomised minute
        hour = random.randint(1, 5)
        minute = random.randint(0, 59)
        trigger = CronTrigger(hour=hour, minute=minute)
        log.info(
            "scheduler.configured",
            mode="safe",
            time=f"{hour:02d}:{minute:02d}",
        )

    else:  # normal
        # Twice per day: early morning + afternoon, randomised minutes
        trigger = CronTrigger(hour="3,15", minute=str(random.randint(0, 30)))
        log.info("scheduler.configured", mode="normal", cron="3,15")

    scheduler.add_job(
        _run_ingestion_job,
        trigger=trigger,
        id="pvp_ingestion",
        name="PVP Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,  # tolerate up to 1h delay (e.g. server restart)
        coalesce=True,            # skip missed runs, do not pile up
    )
    return scheduler


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = build_scheduler()
    return _scheduler


async def start_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        log.info("scheduler.started")


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler.stopped")
    _scheduler = None
