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

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0", alias="REDIS_URL"
    )
    redis_enabled: bool = Field(default=True, alias="REDIS_ENABLED")

    # ── Ingestion ─────────────────────────────────────────────────────────────
    ingestion_mode: Literal["safe", "normal", "dry_run"] = Field(
        default="safe", alias="INGESTION_MODE"
    )
    dry_run: bool = Field(default=False, alias="DRY_RUN")
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
    otlp_endpoint: str = Field(
        default="http://localhost:4317", alias="OTLP_ENDPOINT"
    )

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, v: str) -> str:
        return v.upper()

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


def get_ingestion_mode_config() -> dict:
    cfg = load_yaml_config()
    settings = get_settings()
    mode = settings.ingestion_mode if not settings.is_dry_run else "dry_run"
    return cfg["ingestion"]["modes"][mode]
