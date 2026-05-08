"""
Shared pytest fixtures.
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

# Force dry-run mode for all tests — zero real network I/O.
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("INGESTION_MODE", "dry_run")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://killeraste:killeraste@localhost:5432/killeraste_test",
)
os.environ.setdefault(
    "DATABASE_SYNC_URL",
    "postgresql://killeraste:killeraste@localhost:5432/killeraste_test",
)
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("CONFIG_PATH", "config/config.yaml")

from app.config.settings import get_settings, load_yaml_config  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def yaml_config():
    return load_yaml_config()


@pytest.fixture
def roi_config(yaml_config):
    return yaml_config["roi"]


@pytest.fixture
def risk_config(yaml_config):
    return yaml_config["risk"]
