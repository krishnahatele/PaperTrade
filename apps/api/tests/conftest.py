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


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url=TEST_DB_URL,
        log_json=False,
        log_level="WARNING",
    )


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


@pytest.fixture
async def db_client(migrated_db: None, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    yield client
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE trades, positions, orders, signals, raw_messages, "
                "signal_sources, broker_accounts, instruments, events CASCADE"
            )
        )
    await engine.dispose()
