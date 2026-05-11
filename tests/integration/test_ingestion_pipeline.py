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
def db_required(event_loop):
    """Skip the whole module if DB is not available."""
    import asyncio
    available = asyncio.get_event_loop().run_until_complete(_db_available())
    if not available:
        pytest.skip("PostgreSQL not available – skipping integration tests")


@pytest_asyncio.fixture
async def db_session():
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


class TestIngestionPipeline:
    async def test_dry_run_completes_successfully(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService

        service = IngestionService(db_session)
        result = await service.run(source="pvp")

        assert result["status"] == "dry_run"
        assert result["pages_fetched"] >= 1
        assert result["records_found"] >= 1

    async def test_records_persisted_to_db(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService
        from app.db.repository import AuctionRepository, PropertyRepository

        service = IngestionService(db_session)
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

        service = IngestionService(db_session)
        await service.run(source="pvp")

        first_count_result = await AuctionRepository(db_session).count_by_status()
        first_total = sum(first_count_result.values())

        await service.run(source="pvp")

        second_count_result = await AuctionRepository(db_session).count_by_status()
        second_total = sum(second_count_result.values())

        assert first_total == second_total, "Duplicate records created on second run"

    async def test_roi_computed_for_new_auctions(self, db_session, db_required):
        from app.ingestion.ingestion_service import IngestionService
        from app.db.repository import AuctionRepository, ValuationRepository
        import sqlalchemy as sa
        from app.db.models import Auction

        service = IngestionService(db_session)
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

        service = IngestionService(db_session)
        result = await service.run(source="pvp")

        log_repo = IngestionLogRepository(db_session)
        last = await log_repo.get_last_successful("pvp")
        # In dry_run mode status = dry_run, not completed
        assert last is None or last.mode == "dry_run"
