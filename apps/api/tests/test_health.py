import pytest
from httpx import AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app


async def test_liveness(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "x-request-id" in r.headers


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


async def test_system_info(client: AsyncClient) -> None:
    r = await client.get("/api/v1/system/info")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "0"
    assert body["trading_mode"] == "paper"
    assert body["live_trading_enabled"] is False
    assert set(body["adapters"]) == {"broker", "market_data", "telegram", "llm"}


async def test_readiness_degraded_without_db() -> None:
    from httpx import ASGITransport

    settings = Settings(
        environment=Environment.TEST,
        database_url="postgresql+asyncpg://nobody:nope@127.0.0.1:1/none",
        log_json=False,
        log_level="CRITICAL",
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c,
    ):
        r = await c.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"


@pytest.mark.db
async def test_readiness_ok(db_client: AsyncClient) -> None:
    r = await db_client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == [{"name": "database", "ok": True, "detail": None}]


async def test_openapi_has_no_order_mutation_routes(client: AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    for path, ops in spec["paths"].items():
        if path.startswith("/api/v1/orders"):
            assert set(ops) == {"get"}, f"{path} must be read-only in Phase 0"
