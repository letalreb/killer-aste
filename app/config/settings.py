"""
Centralised configuration.

Priority order (highest to lowest):
  1. Environment variables
  2. .env file
  3. Defaults declared here

Config YAML (config/config.yaml) holds domain-level tuning knobs that
operators adjust without touching code; it is loaded separately via
load_yaml_config().
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_INSECURE_SECRET_KEYS = {
    "",
    "dev-secret-key",
    "change-me-in-production-use-openssl-rand-hex-32",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "Killer Aste Intelligence Platform"
    app_version: str = "1.0.0"
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    secret_key: str = Field(default="dev-secret-key", alias="SECRET_KEY")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://killeraste:killeraste@localhost:5432/killeraste",
        alias="DATABASE_URL",
    )
    database_sync_url: str = Field(
        default="postgresql://killeraste:killeraste@localhost:5432/killeraste",
        alias="DATABASE_SYNC_URL",
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # ── Ingestion ─────────────────────────────────────────────────────────────
    ingestion_mode: Literal["safe", "normal", "dry_run"] = Field(
        default="safe", alias="INGESTION_MODE"
    )
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    # In-process APScheduler. Disable it on hosts that sleep when idle
    # (e.g. Render free plan) and trigger runs from an external cron instead.
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    # Honest, identifiable User-Agent sent to the sources we read.
    ingestion_user_agent: str = Field(
        default="KillerAsteBot/1.0 (+https://github.com/letalreb/killer-aste)",
        alias="INGESTION_USER_AGENT",
    )
    config_path: str = Field(default="config/config.yaml", alias="CONFIG_PATH")

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=1, alias="API_WORKERS")

    # ── Auth ──────────────────────────────────────────────────────────────────
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")

    # ── Monitoring ────────────────────────────────────────────────────────────
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")

    # ── CORS ──────────────────────────────────────────────────────────────────
    frontend_url: str = Field(default="", alias="FRONTEND_URL")

    @field_validator("ingestion_user_agent")
    @classmethod
    def _default_user_agent_if_blank(cls, v: str) -> str:
        return v.strip() or "KillerAsteBot/1.0 (+https://github.com/letalreb/killer-aste)"

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            if self.secret_key in _INSECURE_SECRET_KEYS or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be set to a random value of at least 32 chars "
                    "in production (e.g. `openssl rand -hex 32`)."
                )
            if not self.google_client_id:
                raise ValueError("GOOGLE_CLIENT_ID must be set in production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_dry_run(self) -> bool:
        return self.dry_run or self.ingestion_mode == "dry_run"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def load_yaml_config() -> dict:
    """Load and cache the YAML domain-config file."""
    settings = get_settings()
    path = Path(settings.config_path)
    if not path.exists():
        # Fall back to repo-relative path when running from a sub-directory.
        path = Path(__file__).parents[2] / settings.config_path
    with path.open("r") as fh:
        return yaml.safe_load(fh)


def resolve_ingestion_mode(dry_run: bool | None = None) -> str:
    """Effective ingestion mode. An explicit ``dry_run`` overrides the env setting."""
    settings = get_settings()
    is_dry = settings.is_dry_run if dry_run is None else dry_run
    if is_dry:
        return "dry_run"
    # Explicit real run while INGESTION_MODE=dry_run: fall back to the safest mode.
    return "safe" if settings.ingestion_mode == "dry_run" else settings.ingestion_mode


def get_ingestion_mode_config(dry_run: bool | None = None) -> dict:
    cfg = load_yaml_config()
    return cfg["ingestion"]["modes"][resolve_ingestion_mode(dry_run)]
