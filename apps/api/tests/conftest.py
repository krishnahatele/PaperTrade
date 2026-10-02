"""Shared fixtures.

DB-backed tests run against ``MARKETOS_TEST_DATABASE_URL`` (default: the local
``marketos_test`` database). The schema is rebuilt via Alembic once per
session. If PostgreSQL is unreachable, tests marked ``db`` are skipped.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Environment, Settings
from app.main import create_app

TEST_DB_URL = os.environ.get(
    "MARKETOS_TEST_DATABASE_URL",
    "postgresql+asyncpg://marketos:marketos@localhost:5432/marketos_test",
)
API_ROOT = Path(__file__).resolve().parent.parent


def _db_available() -> bool:
    async def probe() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(asyncio.wait_for(probe(), timeout=5))
    except Exception:
        return False
    return True


DB_AVAILABLE = _db_available()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if DB_AVAILABLE:
        return
    skip = pytest.mark.skip(reason=f"PostgreSQL not reachable at {TEST_DB_URL}")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


TEST_SECRET_KEY = Fernet.generate_key().decode()
ADMIN_PASSWORD = "correct horse battery"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": Environment.TEST,
        "database_url": TEST_DB_URL,
        "log_json": False,
        "log_level": "WARNING",
        "secret_key": TEST_SECRET_KEY,
        "auth_enabled": False,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Auth disabled: for tests that don't exercise authentication."""
    return make_settings()


@pytest.fixture(scope="session")
def auth_settings() -> Settings:
    return make_settings(auth_enabled=True)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _truncate_all() -> None:
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
        ).scalars()
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    await engine.dispose()


@pytest.fixture
async def anon_client(migrated_db: None, auth_settings: Settings) -> AsyncIterator[AsyncClient]:
    """Auth enabled, not logged in, clean database."""
    await _truncate_all()
    app = create_app(auth_settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    await _truncate_all()


@pytest.fixture
async def db_client(anon_client: AsyncClient) -> AsyncClient:
    """Auth enabled and logged in as admin, clean database."""
    r = await anon_client.post("/api/v1/auth/setup", json={"password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    anon_client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return anon_client
