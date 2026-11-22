"""
Auth endpoints and dependencies.

POST /auth/google  – verify Google ID token, upsert user in DB, return JWT
GET  /auth/me      – return current user (role/limits read fresh from DB)

Security notes
──────────────
* Google ID tokens are verified with PyJWT against Google's JWKS. The
  algorithm is pinned to RS256 (never taken from the token header), the
  audience/issuer are checked and ``email_verified`` must be true.
* Our own JWT only identifies the user (``sub``). Role, favourites limit and
  the active flag are always read from the DB, so a role change or a
  deactivation takes effect on the very next request.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.database import get_db
from app.db.models import User, UserRole
from app.db.repository import LoginAuditRepository, UserRepository

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
_security = HTTPBearer(auto_error=False)

_TOKEN_ISSUER = "killer-aste"
_GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
# JWKS client caches Google's public keys (refetched only on unknown kid / after 1h).
_google_jwks = jwt.PyJWKClient(_GOOGLE_CERTS_URL, cache_keys=True, lifespan=3600)


class GoogleTokenRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    sub: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "standard"
    max_favorites: int = 3


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


def _user_out(user: User) -> UserOut:
    return UserOut(
        sub=user.google_sub,
        email=user.email,
        name=user.name,
        picture=user.picture,
        role=user.role.value,
        max_favorites=user.max_favorites,
    )


def _make_token(google_sub: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": google_sub,
            "iss": _TOKEN_ISSUER,
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_db_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    session: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=_TOKEN_ISSUER,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    result = await session.execute(select(User).where(User.google_sub == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")
    return user


async def get_current_user(user: User = Depends(get_current_db_user)) -> UserOut:
    return _user_out(user)


async def require_admin(user: User = Depends(get_current_db_user)) -> UserOut:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return _user_out(user)


def _decode_google_token(token: str, client_id: str) -> dict:
    """Blocking: may fetch Google's JWKS on a cache miss. Run in a thread."""
    signing_key = _google_jwks.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=_GOOGLE_ISSUERS,
        options={"require": ["exp", "iat", "aud", "iss", "sub"]},
    )
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise ValueError("Google account email is not verified")
    return claims


async def _verify_google_id_token(token: str, client_id: str) -> dict:
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")
    return await asyncio.to_thread(_decode_google_token, token, client_id)


@router.post("/google", response_model=TokenResponse)
async def google_login(
    request: Request,
    body: GoogleTokenRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    settings = get_settings()
    try:
        idinfo = await _verify_google_id_token(body.token, settings.google_client_id)
    except Exception as exc:
        log.warning("auth.google_token_invalid", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    user_repo = UserRepository(session)
    db_user = await user_repo.upsert(
        google_sub=idinfo["sub"],
        email=idinfo["email"],
        name=idinfo.get("name", idinfo["email"]),
        picture=idinfo.get("picture"),
    )
    if not db_user.is_active:
        await session.rollback()
        raise HTTPException(status_code=403, detail="Account disabled")

    # request.client is the real peer once uvicorn runs with --proxy-headers and
    # a trusted --forwarded-allow-ips; never read X-Forwarded-For by hand.
    ip = request.client.host if request.client else None
    await LoginAuditRepository(session).create(
        user_id=db_user.id, ip_address=ip, user_agent=request.headers.get("User-Agent")
    )
    await session.commit()

    log.info("auth.login", email=db_user.email, role=db_user.role.value)
    return TokenResponse(
        access_token=_make_token(db_user.google_sub),
        expires_in=settings.jwt_expire_minutes * 60,
        user=_user_out(db_user),
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    return current_user
