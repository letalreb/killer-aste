"""
Unit tests for the anti-ban HTTP client.

All tests run in dry_run mode — zero real network I/O.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from app.ingestion.http_client import AntiBanHTTPClient, DailyCap, _beta_delay


class TestBetaDelay:
    def test_delay_within_bounds(self):
        for _ in range(200):
            d = _beta_delay(1.0, 5.0)
            assert 1.0 <= d <= 5.0

    def test_delay_biased_low(self):
        samples = [_beta_delay(1.0, 10.0) for _ in range(500)]
        mean = sum(samples) / len(samples)
        # Beta(2,5) mean ≈ 0.286, scaled to [1,10] → ~3.6
        assert 2.5 <= mean <= 5.0

    def test_equal_bounds_returns_fixed(self):
        d = _beta_delay(3.0, 3.0)
        assert d == pytest.approx(3.0)


class TestAntiBanHTTPClient:
    @pytest.mark.asyncio
    async def test_dry_run_returns_json_response(self):
        async with AntiBanHTTPClient(dry_run=True) as client:
            resp = await client.post(
                "https://pvp.giustizia.it/ric-496b258c-986a1b71/ric-ms/ricerca/vendite",
                json={"tipoLotto": "IMMOBILI"},
                params={"page": 0, "size": 10},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "body" in data
        assert "content" in data["body"]

    @pytest.mark.asyncio
    async def test_dry_run_no_real_requests(self, monkeypatch):
        import httpx

        real_calls: list = []

        async def patched_send(self, request, **kwargs):
            real_calls.append(request.url)
            raise AssertionError("Dry-run made a real HTTP request!")

        monkeypatch.setattr(httpx.AsyncClient, "send", patched_send)

        async with AntiBanHTTPClient(dry_run=True) as client:
            await client.post(
                "https://pvp.giustizia.it/some/endpoint",
                json={},
                params={"page": 0},
            )

        assert len(real_calls) == 0

    @pytest.mark.asyncio
    async def test_dry_run_paginates_via_params(self):
        async with AntiBanHTTPClient(dry_run=True) as client:
            resp_p0 = await client.post("https://example.com/", json={}, params={"page": 0})
            resp_p1 = await client.post("https://example.com/", json={}, params={"page": 1})

        body_p0 = resp_p0.json()["body"]
        body_p1 = resp_p1.json()["body"]
        assert body_p0["number"] == 0
        assert body_p1["number"] == 1

    @pytest.mark.asyncio
    async def test_daily_cap_enforced(self):
        cfg = {
            "min_delay_seconds": 0.01,
            "max_delay_seconds": 0.02,
            "max_concurrent_requests": 1,
            "daily_request_cap": 3,
            "cooldown_on_429_seconds": 0,
            "cooldown_on_403_seconds": 0,
            "think_time_probability": 0.0,
            "think_time_min_seconds": 0.0,
            "think_time_max_seconds": 0.0,
        }
        async with AntiBanHTTPClient(mode_config=cfg, dry_run=False) as client:
            # Pre-fill counter to ceiling
            client._counter._count = 3
            client._counter._date = date.today()

            with pytest.raises(DailyCap):
                await client.get("https://example.com/")

    @pytest.mark.asyncio
    async def test_session_rotation_resets_counter(self):
        async with AntiBanHTTPClient(dry_run=True) as client:
            original_started = client._session_started_at
            client._session_request_count = 999
            await client._maybe_rotate_session()

            assert client._session_request_count == 0
            assert client._session_started_at >= original_started

    @pytest.mark.asyncio
    async def test_get_method_also_works_dry_run(self):
        async with AntiBanHTTPClient(dry_run=True) as client:
            resp = await client.get("https://pvp.giustizia.it/some/page", params={"page": 0})
        assert resp.status_code == 200

    def test_counter_resets_on_new_day(self):
        from app.ingestion.http_client import _InMemoryRequestCounter
        from datetime import date, timedelta

        counter = _InMemoryRequestCounter()
        counter._count = 50
        counter._date = date.today() - timedelta(days=1)  # yesterday

        assert counter.today_count() == 0
        n = counter.increment()
        assert n == 1

    @pytest.mark.asyncio
    async def test_cooldown_set_and_clears(self):
        import time

        async with AntiBanHTTPClient(dry_run=True) as client:
            client._set_cooldown(0)  # already expired
            await client._wait_for_cooldown()  # should not sleep
            assert client._cooldown_until is None
