"""Settings validation, Google token verification and polite client behaviour."""
from __future__ import annotations

import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import Settings


class TestProductionSettings:
    def test_default_secret_rejected_in_production(self):
        with pytest.raises(ValueError, match="SECRET_KEY"):
            Settings(APP_ENV="production", SECRET_KEY="dev-secret-key", GOOGLE_CLIENT_ID="x")

    def test_short_secret_rejected_in_production(self):
        with pytest.raises(ValueError, match="SECRET_KEY"):
            Settings(APP_ENV="production", SECRET_KEY="short", GOOGLE_CLIENT_ID="x")

    def test_missing_google_client_id_rejected_in_production(self):
        with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
            Settings(APP_ENV="production", SECRET_KEY="a" * 64, GOOGLE_CLIENT_ID="")

    def test_valid_production_settings(self):
        s = Settings(APP_ENV="production", SECRET_KEY="a" * 64, GOOGLE_CLIENT_ID="x")
        assert s.is_production

    def test_development_allows_defaults(self):
        assert Settings(APP_ENV="development").secret_key == "dev-secret-key"


# ── Google ID token verification ─────────────────────────────────────────────

CLIENT_ID = "test-client.apps.googleusercontent.com"
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    key = _key.public_key()


class _FakeJWKS:
    def get_signing_key_from_jwt(self, _token):
        return _FakeSigningKey()


@pytest.fixture
def fake_google(monkeypatch):
    from app.api.routes import auth

    monkeypatch.setattr(auth, "_google_jwks", _FakeJWKS())
    return auth


def _google_token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "123",
        "email": "a@b.it", "email_verified": True, "iat": now, "exp": now + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, _key, algorithm="RS256", headers={"kid": "k1"})


class TestGoogleVerification:
    async def test_valid_token(self, fake_google):
        claims = await fake_google._verify_google_id_token(_google_token(), CLIENT_ID)
        assert claims["sub"] == "123"

    async def test_unverified_email_rejected(self, fake_google):
        with pytest.raises(ValueError, match="not verified"):
            await fake_google._verify_google_id_token(
                _google_token(email_verified=False), CLIENT_ID
            )

    async def test_wrong_audience_rejected(self, fake_google):
        with pytest.raises(jwt.InvalidAudienceError):
            await fake_google._verify_google_id_token(_google_token(aud="other"), CLIENT_ID)

    async def test_wrong_issuer_rejected(self, fake_google):
        with pytest.raises(jwt.InvalidIssuerError):
            await fake_google._verify_google_id_token(
                _google_token(iss="https://evil.example"), CLIENT_ID
            )

    async def test_hs256_token_rejected(self, fake_google):
        """Algorithm is pinned to RS256: an HMAC-signed token must never pass."""
        now = int(time.time())
        token = jwt.encode(
            {"iss": "accounts.google.com", "aud": CLIENT_ID, "sub": "1", "email": "a@b.it",
             "email_verified": True, "iat": now, "exp": now + 600},
            "x" * 32, algorithm="HS256",
        )
        with pytest.raises(jwt.InvalidAlgorithmError):
            await fake_google._verify_google_id_token(token, CLIENT_ID)

    async def test_empty_client_id_rejected(self, fake_google):
        with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
            await fake_google._verify_google_id_token(_google_token(), "")


# ── Polite HTTP client ────────────────────────────────────────────────────────

_CFG = {
    "min_delay_seconds": 0.0, "max_delay_seconds": 0.0, "max_concurrent_requests": 1,
    "daily_request_cap": 10, "cooldown_on_429_seconds": 0, "cooldown_on_403_seconds": 0,
}


class TestPoliteClient:
    def test_retry_after_seconds_and_dates(self):
        from email.utils import formatdate

        from app.ingestion.http_client import _parse_retry_after

        assert _parse_retry_after("120") == 120
        assert _parse_retry_after(None) == 0
        assert _parse_retry_after("garbage") == 0
        in_a_minute = formatdate(time.time() + 60, usegmt=True)
        assert 55 <= _parse_retry_after(in_a_minute) <= 60

    async def test_identifiable_user_agent(self):
        from app.ingestion.http_client import PoliteHTTPClient

        async with PoliteHTTPClient(mode_config=_CFG, dry_run=False) as client:
            assert client._client.headers["User-Agent"].startswith("KillerAsteBot/")

    async def test_403_stops_without_cooldown(self, monkeypatch):
        from app.ingestion.http_client import AccessDenied, PoliteHTTPClient

        async def _forbidden(self, method, url, **kw):
            return httpx.Response(403, request=httpx.Request(method, url))

        monkeypatch.setattr(httpx.AsyncClient, "request", _forbidden)
        async with PoliteHTTPClient(mode_config=_CFG, dry_run=False) as client:
            with pytest.raises(AccessDenied):
                await client.get("https://example.com/")
            assert client._cooldown_until is None

    async def test_daily_cap_seeded_from_previous_runs(self):
        from app.ingestion.http_client import DailyCap, PoliteHTTPClient

        async with PoliteHTTPClient(
            mode_config=_CFG, dry_run=False, initial_request_count=10
        ) as client:
            with pytest.raises(DailyCap):
                await client.get("https://example.com/")
