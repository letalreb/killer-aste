"""
FastAPI application entrypoint.

Lifespan:
- startup  → configure logging, start scheduler
- shutdown → stop scheduler, close DB pool
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analytics, auctions, properties
from app.config.settings import get_settings
from app.ingestion.scheduler import start_scheduler, stop_scheduler

settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
#  Structured logging
# ─────────────────────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
            if settings.is_production
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _configure_logging()
    log = structlog.get_logger(__name__)
    log.info(
        "app.startup",
        name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
        mode=settings.ingestion_mode,
        dry_run=settings.is_dry_run,
    )
    await start_scheduler()
    yield
    log.info("app.shutdown")
    await stop_scheduler()


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
if settings.enable_metrics:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    except ImportError:
        pass

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(auctions.router, prefix="/api/v1")
app.include_router(properties.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")


# ─────────────────────────────────────────────────────────────────────────────
#  Global exception handler
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log = structlog.get_logger(__name__)
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Health & readiness
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "version": settings.app_version}


@app.get("/ready", tags=["ops"])
async def readiness() -> dict:
    """Check DB connectivity."""
    from app.db.database import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": str(exc)},
        )
