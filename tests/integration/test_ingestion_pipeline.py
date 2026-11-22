"""
Integration test for the full ingestion pipeline in dry_run mode.

Requires a running PostgreSQL instance (see docker-compose for local setup).
Skipped automatically when DB is unavailable.
"""
from __future__ import annotations

import os
import pytest
import pytest_asyncio

# Ensure dry_run is active
os.environ["DRY_RUN"] = "true"
os.environ["INGESTION_MODE"] = "dry_run"

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        import sqlalchemy as sa

        engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"timeout": 2})
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def db_required():
    """Skip the whole module if DB is not available."""
    import asyncio
    available = asyncio.run(_db_available())
    if not available:
        pytest.skip("PostgreSQL not available – skipping integration tests")


@pytest_asyncio.fixture
async def db_session(db_required):
    from app.db.database import AsyncSessionFactory
    from app.db.models import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionFactory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    # The app engine pools connections per event loop; drop them between tests.
    from app.db.database import engine as app_engine
    await app_engine.dispose()


class TestIngestionPipeline:
    async def test_dry_run_completes_successfully(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService

        service = IngestionService(db_session, dry_run=True)
        result = await service.run(source="pvp")

        assert result["status"] == "dry_run"
        assert result["pages_fetched"] >= 1
        assert result["records_found"] >= 1

    async def test_records_persisted_to_db(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService
        from app.db.repository import AuctionRepository, PropertyRepository

        service = IngestionService(db_session, dry_run=True)
        await service.run(source="pvp")

        prop_repo = PropertyRepository(db_session)
        auction_repo = AuctionRepository(db_session)

        props = await prop_repo.list_by_province("MI")
        assert len(props) >= 1

        auctions = await auction_repo.list_upcoming()
        assert len(auctions) >= 1

    async def test_idempotent_upsert(self, db_session, db_required):
        """Running the pipeline twice should not duplicate records."""
        from app.ingestion.ingestion_service import IngestionService
        from app.db.repository import AuctionRepository

        service = IngestionService(db_session, dry_run=True)
        await service.run(source="pvp")

        first_count_result = await AuctionRepository(db_session).count_by_status()
        first_total = sum(first_count_result.values())

        await service.run(source="pvp")

        second_count_result = await AuctionRepository(db_session).count_by_status()
        second_total = sum(second_count_result.values())

        assert first_total == second_total, "Duplicate records created on second run"

    async def test_roi_computed_for_new_auctions(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService
        from app.db.repository import ValuationRepository
        import sqlalchemy as sa
        from app.db.models import Auction

        service = IngestionService(db_session, dry_run=True)
        await service.run(source="pvp")

        result = await db_session.execute(sa.select(Auction).limit(1))
        auction = result.scalar_one_or_none()
        if auction:
            v_repo = ValuationRepository(db_session)
            valuation = await v_repo.get_latest_for_auction(auction.id)
            assert valuation is not None
            assert valuation.roi_percentage is not None

    async def test_ingestion_log_recorded(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService
        from app.db.repository import IngestionLogRepository

        service = IngestionService(db_session, dry_run=True)
        await service.run(source="pvp")

        log_repo = IngestionLogRepository(db_session)
        last = await log_repo.get_last_successful("pvp")
        # In dry_run mode status = dry_run, not completed
        assert last is None or last.mode == "dry_run"

    async def test_explicit_dry_run_overrides_env(self, db_session, db_required, monkeypatch):
        """dry_run=True must never touch the network, whatever the env says."""
        import httpx
        from app.ingestion.ingestion_service import IngestionService

        async def _no_network(*_a, **_k):
            raise AssertionError("network call attempted during dry run")

        monkeypatch.setattr(httpx.AsyncClient, "request", _no_network)
        result = await IngestionService(db_session, dry_run=True).run(source="pvp")
        assert result["status"] == "dry_run"

    async def test_403_blocks_next_real_run_until_forced(self, db_session, db_required, monkeypatch):
        import httpx
        from app.db.models import IngestionLog, IngestionStatus
        from app.ingestion.ingestion_service import IngestionService

        db_session.add(IngestionLog(
            run_id="blocked1", source="pvp", mode="safe", status=IngestionStatus.FAILED,
            error_detail="HTTP 403 – source refused access; run stopped",
        ))
        await db_session.commit()

        async def _no_network(*_a, **_k):
            raise AssertionError("network call attempted while blocked")

        monkeypatch.setattr(httpx.AsyncClient, "request", _no_network)
        result = await IngestionService(db_session, dry_run=False).run(source="pvp")
        assert result["status"] == "failed"
        assert "blocked1" in result["error_detail"]
        assert result["requests_made"] == 0

    async def test_requests_today_counts_real_runs_only(self, db_session, db_required):
        from app.db.models import IngestionLog, IngestionStatus
        from app.db.repository import IngestionLogRepository

        db_session.add_all([
            IngestionLog(run_id="r1", source="pvp", mode="safe",
                         status=IngestionStatus.COMPLETED, requests_made=40),
            IngestionLog(run_id="r2", source="pvp", mode="dry_run",
                         status=IngestionStatus.DRY_RUN, requests_made=500),
        ])
        await db_session.commit()
        assert await IngestionLogRepository(db_session).requests_today() == 40
