"""
Auth endpoints.

POST /auth/google  – verify Google ID token, return JWT
GET  /auth/me      – return current user from JWT
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config.settings import get_settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
_security = HTTPBearer(auto_error=False)


class GoogleTokenRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    sub: str
    email: str
    name: str
    picture: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


def _make_token(user: UserOut) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {
            "sub": user.sub,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "exp": expire,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> UserOut:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return UserOut(
            sub=payload["sub"],
            email=payload["email"],
            name=payload["name"],
            picture=payload.get("picture"),
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


@router.post("/google", response_model=TokenResponse)
async def google_login(request: GoogleTokenRequest) -> TokenResponse:
    settings = get_settings()
    try:
        from google.oauth2 import id_token  # type: ignore[import-untyped]
        from google.auth.transport import requests as google_requests  # type: ignore[import-untyped]

        idinfo = id_token.verify_oauth2_token(
            request.token,
            google_requests.Request(),
            settings.google_client_id,
        )
        user = UserOut(
            sub=idinfo["sub"],
            email=idinfo["email"],
            name=idinfo.get("name", idinfo["email"]),
            picture=idinfo.get("picture"),
        )
    except Exception as exc:
        log.warning("auth.google_token_invalid", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    token = _make_token(user)
    log.info("auth.login", email=user.email)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=user,
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    return current_user
