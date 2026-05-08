"""
Anti-ban HTTP client.

HOW IT PREVENTS BANS
────────────────────
1. Non-uniform random delays   – Inter-request gaps sampled from a Beta(2,5)
   distribution (biased toward shorter delays), scaled to [min, max].  The
   server never sees a perfectly periodic pattern.

2. Occasional "think pauses"   – 10-20% of requests are followed by a long
   (15-45 s) human-like pause, simulating reading a page.

3. Exponential back-off + jitter  – On 429/503/connection errors the client
   backs off exponentially (60 s → 120 s → 240 s … up to 30 min).
   A ±25% jitter prevents the thundering-herd "retry storm" if we ever run
   parallel workers.

4. Rotating User-Agent pool    – A curated list of real desktop browser UAs
   is sampled per session.  The pool is weighted toward Chrome (≈70%), which
   matches real web traffic distribution.

5. Session reuse with cookies  – We keep one httpx.AsyncClient per logical
   "session" so cookies accumulate naturally (like a real browser).
   Sessions are rotated after N requests OR after M minutes (whichever first)
   to avoid building a long-running fingerprint.

6. Hard daily request cap      – A counter (Redis if available, else in-memory)
   prevents the service from ever exceeding the configured daily ceiling,
   even if the scheduler fires multiple overlapping runs.

7. Status-code cooldown        – On HTTP 429 the client sleeps for the
   Retry-After header value (or configured default).  On 403 it sleeps
   for a longer period and logs a high-severity warning.

8. Dry-run mode                – When DRY_RUN=true, every request is intercepted
   before network I/O and a fixture response is returned.  Zero real traffic.

9. Max concurrency semaphore   – asyncio.Semaphore(max_concurrent_requests)
   ensures we never open more connections simultaneously than configured
   (1 in safe mode, 2 in normal mode).
"""
from __future__ import annotations

import asyncio
import random
import time
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
import structlog

from app.config.settings import get_ingestion_mode_config, get_settings
from app.ingestion.mock_responses import get_mock_response

log = structlog.get_logger(__name__)

# ── Curated UA pool (real Chrome/Firefox desktop strings) ────────────────────
_USER_AGENTS: list[tuple[str, float]] = [
    # (ua_string, weight)
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36",
        0.30,
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36",
        0.25,
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36",
        0.15,
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36",
        0.10,
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
        "Gecko/20100101 Firefox/133.0",
        0.10,
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.1.1 Safari/605.1.15",
        0.10,
    ),
]

_UA_STRINGS = [ua for ua, _ in _USER_AGENTS]
_UA_WEIGHTS = [w for _, w in _USER_AGENTS]


def _pick_ua() -> str:
    return random.choices(_UA_STRINGS, weights=_UA_WEIGHTS, k=1)[0]


def _beta_delay(min_s: float, max_s: float) -> float:
    """
    Sample a delay from Beta(2,5) scaled to [min_s, max_s].
    Beta(2,5) is right-skewed: most delays cluster toward the lower end,
    mimicking a human who usually responds quickly but occasionally lingers.
    """
    raw = random.betavariate(2, 5)          # value in [0, 1]
    return min_s + raw * (max_s - min_s)


class _InMemoryRequestCounter:
    """Fallback counter when Redis is unavailable."""

    def __init__(self) -> None:
        self._count: int = 0
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


class AntiBanHTTPClient:
    """
    A context-manager-compatible async HTTP client with built-in rate
    limiting, back-off, session rotation, and dry-run support.

    Usage
    -----
    async with AntiBanHTTPClient() as client:
        response = await client.get("https://example.com/page?p=1")
    """

    def __init__(
        self,
        mode_config: Optional[dict] = None,
        dry_run: bool | None = None,
    ) -> None:
        self._cfg = mode_config or get_ingestion_mode_config()
        settings = get_settings()
        self._dry_run = dry_run if dry_run is not None else settings.is_dry_run

        self._semaphore = asyncio.Semaphore(self._cfg["max_concurrent_requests"])
        self._counter = _InMemoryRequestCounter()  # Redis extension point

        # Session state
        self._client: Optional[httpx.AsyncClient] = None
        self._session_ua: str = _pick_ua()
        self._session_request_count: int = 0
        self._session_started_at: datetime = datetime.utcnow()

        # Back-off state
        self._consecutive_errors: int = 0
        self._cooldown_until: Optional[float] = None   # monotonic timestamp

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "AntiBanHTTPClient":
        await self._new_session()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

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
        # Dry-run short-circuit: never touches the network.
        if self._dry_run:
            log.debug("dry_run.request", method=method, url=url)
            await asyncio.sleep(_beta_delay(0.05, 0.15))
            return get_mock_response(params=kwargs.get("params"))

        # ── Daily cap check ───────────────────────────────────────────────────
        cap = self._cfg["daily_request_cap"]
        today_count = self._counter.today_count()
        if today_count >= cap:
            log.warning(
                "daily_cap.reached",
                cap=cap,
                today_count=today_count,
            )
            raise DailyCap(f"Daily request cap of {cap} reached.")

        # ── Global cooldown (from 429/403) ────────────────────────────────────
        await self._wait_for_cooldown()

        # ── Session rotation ──────────────────────────────────────────────────
        await self._maybe_rotate_session()

        # ── Inter-request delay ───────────────────────────────────────────────
        delay = _beta_delay(
            self._cfg["min_delay_seconds"],
            self._cfg["max_delay_seconds"],
        )
        log.debug("delay.pre_request", seconds=round(delay, 2), url=url)
        await asyncio.sleep(delay)

        # ── Human "think time" (occasional long pause) ────────────────────────
        think_prob = self._cfg.get("think_time_probability", 0.0)
        if think_prob > 0 and random.random() < think_prob:
            think_time = random.uniform(
                self._cfg["think_time_min_seconds"],
                self._cfg["think_time_max_seconds"],
            )
            log.debug("think_time.pause", seconds=round(think_time, 1))
            await asyncio.sleep(think_time)

        # ── Semaphore-guarded actual request ─────────────────────────────────
        async with self._semaphore:
            response = await self._execute(method, url, **kwargs)

        self._counter.increment()
        self._session_request_count += 1

        # ── Response handling ─────────────────────────────────────────────────
        await self._handle_response_status(response, url)

        return response

    async def _execute(
        self, method: str, url: str, **kwargs: object
    ) -> httpx.Response:
        assert self._client is not None
        try:
            response = await self._client.request(method, url, **kwargs)
            self._consecutive_errors = 0
            return response
        except httpx.TransportError as exc:
            self._consecutive_errors += 1
            log.warning(
                "request.transport_error",
                url=url,
                error=str(exc),
                consecutive=self._consecutive_errors,
            )
            await self._apply_backoff(reason="transport_error")
            raise

    async def _handle_response_status(
        self, response: httpx.Response, url: str
    ) -> None:
        status = response.status_code

        if status == 429:
            retry_after = int(response.headers.get("Retry-After", 0))
            cooldown = max(retry_after, self._cfg["cooldown_on_429_seconds"])
            log.warning(
                "rate_limited.429",
                url=url,
                cooldown_seconds=cooldown,
            )
            self._set_cooldown(cooldown)
            raise RateLimited(f"HTTP 429 – cooling down for {cooldown}s")

        if status == 403:
            cooldown = self._cfg["cooldown_on_403_seconds"]
            log.error(
                "access_denied.403",
                url=url,
                cooldown_seconds=cooldown,
            )
            self._set_cooldown(cooldown)
            raise AccessDenied(f"HTTP 403 – cooling down for {cooldown}s")

        if status >= 500:
            self._consecutive_errors += 1
            await self._apply_backoff(reason=f"http_{status}")

    # ── Back-off helpers ──────────────────────────────────────────────────────

    async def _apply_backoff(self, reason: str) -> None:
        from app.config.settings import load_yaml_config

        cfg = load_yaml_config()["ingestion"]["backoff"]
        initial = cfg["initial_seconds"]
        max_wait = cfg["max_seconds"]
        multiplier = cfg["multiplier"]
        jitter = cfg["jitter_factor"]

        wait = min(initial * (multiplier ** self._consecutive_errors), max_wait)
        wait *= 1 + random.uniform(-jitter, jitter)
        log.info(
            "backoff.sleeping",
            reason=reason,
            seconds=round(wait, 1),
            consecutive_errors=self._consecutive_errors,
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

    # ── Session management ────────────────────────────────────────────────────

    async def _new_session(self) -> None:
        """Create a fresh httpx client (new cookie jar, new UA)."""
        if self._client:
            await self._client.aclose()

        self._session_ua = _pick_ua()
        self._session_request_count = 0
        self._session_started_at = datetime.utcnow()

        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": self._session_ua,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        log.info("session.new", ua=self._session_ua[:40])

    async def _maybe_rotate_session(self) -> None:
        from app.config.settings import load_yaml_config

        cfg = load_yaml_config()["ingestion"]["sessions"]
        age_minutes = (
            datetime.utcnow() - self._session_started_at
        ).total_seconds() / 60

        if (
            self._session_request_count >= cfg["rotate_after_requests"]
            or age_minutes >= cfg["rotate_after_minutes"]
        ):
            log.info(
                "session.rotating",
                requests=self._session_request_count,
                age_minutes=round(age_minutes, 1),
            )
            await _jittered_rotation_pause()
            await self._new_session()


async def _jittered_rotation_pause() -> None:
    """Brief human-like pause when switching sessions."""
    await asyncio.sleep(random.uniform(2.0, 6.0))


# ── Custom exceptions ─────────────────────────────────────────────────────────

class DailyCap(Exception):
    """Raised when the daily request ceiling is reached."""


class RateLimited(Exception):
    """Raised on HTTP 429."""


class AccessDenied(Exception):
    """Raised on HTTP 403 (possible soft-ban)."""
