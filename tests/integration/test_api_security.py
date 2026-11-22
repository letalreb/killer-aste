"""
API-level security tests: auth, admin guard, favorites limit.

Requires PostgreSQL (skipped otherwise), like the ingestion pipeline tests.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    try:
        import sqlalchemy as sa
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"timeout": 2})
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def db_required():
    import asyncio

    if not asyncio.run(_db_available()):
        pytest.skip("PostgreSQL not available – skipping API tests")


@pytest_asyncio.fixture
async def ctx(db_required):
    """Fresh schema + two users (standard, admin) + three auctions."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.api.main import app
    from app.api.routes.auth import _make_token
    from app.db.database import AsyncSessionFactory
    from app.db.database import engine as app_engine
    from app.db.models import Auction, Base, Property, User, UserRole

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionFactory() as s:
        std = User(google_sub="std-1", email="std@x.it", name="Std", max_favorites=2)
        adm = User(
            google_sub="adm-1", email="adm@x.it", name="Adm",
            role=UserRole.ADMIN, max_favorites=999,
        )
        prop = Property(external_id="p1", city="Milano", province="MI")
        s.add_all([std, adm, prop])
        await s.flush()
        auctions = [
            Auction(property_id=prop.id, external_id=f"a{i}", base_price=100_000 + i)
            for i in range(3)
        ]
        s.add_all(auctions)
        await s.commit()
        auction_ids = [str(a.id) for a in auctions]
        std_id = std.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "std": {"Authorization": f"Bearer {_make_token('std-1')}"},
            "adm": {"Authorization": f"Bearer {_make_token('adm-1')}"},
            "auctions": auction_ids,
            "std_id": std_id,
        }

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    await app_engine.dispose()


class TestAuth:
    async def test_requires_token(self, ctx):
        r = await ctx["client"].get("/api/v1/auctions")
        assert r.status_code == 401

    async def test_forged_token_rejected(self, ctx):
        import jwt

        forged = jwt.encode({"sub": "adm-1", "iss": "killer-aste", "exp": 9999999999},
                            "wrong-key", algorithm="HS256")
        r = await ctx["client"].get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 401

    async def test_disabled_user_rejected(self, ctx):
        from sqlalchemy import update

        from app.db.database import AsyncSessionFactory
        from app.db.models import User

        async with AsyncSessionFactory() as s:
            await s.execute(update(User).where(User.google_sub == "std-1").values(is_active=False))
            await s.commit()
        r = await ctx["client"].get("/auth/me", headers=ctx["std"])
        assert r.status_code == 401


class TestAdminGuard:
    async def test_public_trigger_endpoint_removed(self, ctx):
        r = await ctx["client"].post(
            "/api/v1/auctions/trigger-ingestion", json={"dry_run": True}, headers=ctx["std"]
        )
        assert r.status_code in (404, 405)

    async def test_standard_user_cannot_trigger(self, ctx):
        r = await ctx["client"].post(
            "/api/v1/admin/ingestion/trigger", json={"dry_run": True}, headers=ctx["std"]
        )
        assert r.status_code == 403

    async def test_role_change_applies_immediately(self, ctx):
        """Demoting an admin must take effect without waiting for token expiry."""
        from sqlalchemy import update

        from app.db.database import AsyncSessionFactory
        from app.db.models import User, UserRole

        r = await ctx["client"].get("/api/v1/admin/users", headers=ctx["adm"])
        assert r.status_code == 200
        async with AsyncSessionFactory() as s:
            await s.execute(
                update(User).where(User.google_sub == "adm-1").values(role=UserRole.STANDARD)
            )
            await s.commit()
        r = await ctx["client"].get("/api/v1/admin/users", headers=ctx["adm"])
        assert r.status_code == 403

    async def test_admin_cannot_demote_self(self, ctx):
        from sqlalchemy import select

        from app.db.database import AsyncSessionFactory
        from app.db.models import User

        async with AsyncSessionFactory() as s:
            adm_id = (await s.execute(select(User.id).where(User.google_sub == "adm-1"))).scalar_one()
        r = await ctx["client"].patch(
            f"/api/v1/admin/users/{adm_id}/role", json={"role": "standard"}, headers=ctx["adm"]
        )
        assert r.status_code == 400


class TestFavorites:
    async def test_limit_enforced_server_side(self, ctx):
        c, h, a = ctx["client"], ctx["std"], ctx["auctions"]
        assert (await c.put(f"/api/v1/favorites/{a[0]}", headers=h)).status_code == 200
        r = await c.put(f"/api/v1/favorites/{a[1]}", headers=h)
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2
        r = await c.put(f"/api/v1/favorites/{a[2]}", headers=h)
        assert r.status_code == 409

    async def test_add_is_idempotent_and_remove_works(self, ctx):
        c, h, a = ctx["client"], ctx["std"], ctx["auctions"]
        await c.put(f"/api/v1/favorites/{a[0]}", headers=h)
        r = await c.put(f"/api/v1/favorites/{a[0]}", headers=h)
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["label"] == "Milano (MI)"
        assert (await c.delete(f"/api/v1/favorites/{a[0]}", headers=h)).status_code == 204
        r = await c.get("/api/v1/favorites", headers=h)
        assert r.json() == {"max_favorites": 2, "items": []}

    async def test_unknown_auction_404(self, ctx):
        r = await ctx["client"].put(f"/api/v1/favorites/{uuid.uuid4()}", headers=ctx["std"])
        assert r.status_code == 404

    async def test_favorites_are_per_user(self, ctx):
        c, a = ctx["client"], ctx["auctions"]
        await c.put(f"/api/v1/favorites/{a[0]}", headers=ctx["std"])
        r = await c.get("/api/v1/favorites", headers=ctx["adm"])
        assert r.json()["items"] == []


class TestOps:
    async def test_ready_does_not_leak_errors(self, ctx):
        r = await ctx["client"].get("/ready")
        assert r.status_code == 200
        assert set(r.json()) == {"status"}
