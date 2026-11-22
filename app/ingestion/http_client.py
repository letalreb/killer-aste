"""
Polite HTTP client for public-data sources.

The goal is to read public auction data *without* burdening the source and
*without* hiding who we are:

1. Identifiable User-Agent      – One fixed UA (INGESTION_USER_AGENT) that
   names the project and a contact URL. No UA rotation, no browser spoofing.

2. Randomised inter-request gap – Delays sampled from Beta(2,5) scaled to
   [min, max] seconds, so requests are spread out rather than bursty.

3. Exponential back-off + jitter – On 5xx/connection errors the client backs
   off exponentially (60 s → 120 s → … up to 30 min).

4. Hard daily request cap       – The caller passes how many requests were
   already made today (persisted in ingestion_logs), so the ceiling holds
   across process restarts.

5. Respect for refusals         – On 429 we honour Retry-After (or the
   configured cooldown) and abort the run. On 403 we abort the run; the
   ingestion service then refuses to run again until an admin forces it.

6. Dry-run mode                 – When dry_run is true, every request is
   intercepted before network I/O and a fixture response is returned.

7. Max concurrency semaphore    – asyncio.Semaphore(max_concurrent_requests).
"""
from __future__ import annotations

import asyncio
import random
import time
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx
import structlog

from app.config.settings import get_ingestion_mode_config, get_settings
from app.ingestion.mock_responses import get_mock_response

log = structlog.get_logger(__name__)


def _beta_delay(min_s: float, max_s: float) -> float:
    """Sample a delay from Beta(2,5) scaled to [min_s, max_s]."""
    raw = random.betavariate(2, 5)          # value in [0, 1]
    return min_s + raw * (max_s - min_s)


def _parse_retry_after(value: Optional[str]) -> int:
    """Retry-After may be delta-seconds or an HTTP date (RFC 9110)."""
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        return max(0, int(retry_at.timestamp() - time.time()))
    except (TypeError, ValueError):
        return 0


class _DailyRequestCounter:
    """Per-day counter, seeded with the requests already made today."""

    def __init__(self, initial: int = 0) -> None:
        self._count: int = initial
        self._date: date = date.today()

    def increment(self) -> int:
        today = date.today()
        if today != self._date:
            self._count = 0
            self._date = today
        self._count += 1
        return self._count

    def today_count(self) -> int:
        if date.today() != self._date:
            return 0
        return self._count


class PoliteHTTPClient:
    """
    Async context manager with rate limiting, back-off and dry-run support.

    Usage
    -----
    async with PoliteHTTPClient(initial_request_count=n) as client:
        response = await client.get("https://example.com/page?p=1")
    """

    def __init__(
        self,
        mode_config: Optional[dict] = None,
        dry_run: bool | None = None,
        initial_request_count: int = 0,
    ) -> None:
        settings = get_settings()
        self._dry_run = dry_run if dry_run is not None else settings.is_dry_run
        self._cfg = mode_config or get_ingestion_mode_config(self._dry_run)
        self._user_agent = settings.ingestion_user_agent

        self._semaphore = asyncio.Semaphore(self._cfg["max_concurrent_requests"])
        self._counter = _DailyRequestCounter(initial_request_count)
        self.requests_made: int = 0      # real requests sent by this client
        self._client: Optional[httpx.AsyncClient] = None

        # Back-off state
        self._consecutive_errors: int = 0
        self._cooldown_until: Optional[float] = None   # monotonic timestamp

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "PoliteHTTPClient":
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "it-IT,it;q=0.9",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def requests_today(self) -> int:
        return self._counter.today_count()

    # ── Public API ────────────────────────────────────────────────────────────

    async def get(
        self, url: str, params: Optional[dict] = None, **kwargs: object
    ) -> httpx.Response:
        return await self._request("GET", url, params=params, **kwargs)

    async def post(
        self,
        url: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        **kwargs: object,
    ) -> httpx.Response:
        return await self._request("POST", url, json=json, params=params, **kwargs)

    # ── Core request logic ────────────────────────────────────────────────────

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        if self._dry_run:
            log.debug("dry_run.request", method=method, url=url)
            await asyncio.sleep(_beta_delay(0.05, 0.15))
            return get_mock_response(params=kwargs.get("params"))

        cap = self._cfg["daily_request_cap"]
        today_count = self._counter.today_count()
        if today_count >= cap:
            log.warning("daily_cap.reached", cap=cap, today_count=today_count)
            raise DailyCap(f"Daily request cap of {cap} reached.")

        await self._wait_for_cooldown()

        delay = _beta_delay(self._cfg["min_delay_seconds"], self._cfg["max_delay_seconds"])
        log.debug("delay.pre_request", seconds=round(delay, 2), url=url)
        await asyncio.sleep(delay)

        async with self._semaphore:
            response = await self._execute(method, url, **kwargs)

        self._counter.increment()
        self.requests_made += 1
        await self._handle_response_status(response, url)
        return response

    async def _execute(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        assert self._client is not None, "use PoliteHTTPClient as an async context manager"
        try:
            response = await self._client.request(method, url, **kwargs)
            self._consecutive_errors = 0
            return response
        except httpx.TransportError as exc:
            self._consecutive_errors += 1
            log.warning(
                "request.transport_error",
                url=url, error=str(exc), consecutive=self._consecutive_errors,
            )
            await self._apply_backoff(reason="transport_error")
            raise

    async def _handle_response_status(self, response: httpx.Response, url: str) -> None:
        status = response.status_code

        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            cooldown = max(retry_after, self._cfg["cooldown_on_429_seconds"])
            log.warning("rate_limited.429", url=url, cooldown_seconds=cooldown)
            self._set_cooldown(cooldown)
            raise RateLimited(f"HTTP 429 – cooling down for {cooldown}s")

        if status == 403:
            # A 403 is a refusal, not a transient error: stop, don't retry.
            log.error("access_denied.403", url=url)
            raise AccessDenied("HTTP 403 – source refused access; run stopped")

        if status >= 500:
            self._consecutive_errors += 1
            await self._apply_backoff(reason=f"http_{status}")

    # ── Back-off helpers ──────────────────────────────────────────────────────

    async def _apply_backoff(self, reason: str) -> None:
        from app.config.settings import load_yaml_config

        cfg = load_yaml_config()["ingestion"]["backoff"]
        wait = min(
            cfg["initial_seconds"] * (cfg["multiplier"] ** self._consecutive_errors),
            cfg["max_seconds"],
        )
        wait *= 1 + random.uniform(-cfg["jitter_factor"], cfg["jitter_factor"])
        log.info(
            "backoff.sleeping",
            reason=reason, seconds=round(wait, 1), consecutive_errors=self._consecutive_errors,
        )
        await asyncio.sleep(wait)

    def _set_cooldown(self, seconds: int) -> None:
        self._cooldown_until = time.monotonic() + seconds

    async def _wait_for_cooldown(self) -> None:
        if self._cooldown_until is None:
            return
        remaining = self._cooldown_until - time.monotonic()
        if remaining > 0:
            log.info("cooldown.waiting", seconds=round(remaining, 1))
            await asyncio.sleep(remaining)
        self._cooldown_until = None


# ── Custom exceptions ─────────────────────────────────────────────────────────

class DailyCap(Exception):
    """Raised when the daily request ceiling is reached."""


class RateLimited(Exception):
    """Raised on HTTP 429."""


class AccessDenied(Exception):
    """Raised on HTTP 403."""
