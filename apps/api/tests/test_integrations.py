import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.db

API_HASH = "0123456789abcdef0123456789abcdef"


async def test_credentials_are_write_only_and_encrypted(db_client: AsyncClient) -> None:
    r = await db_client.get("/api/v1/integrations")
    body = r.json()
    assert body["telegram"]["api_id"] == {"set": False, "hint": None}
    assert body["telegram"]["authorized"] is False

    r = await db_client.put(
        "/api/v1/integrations/telegram",
        json={"api_id": "123456", "api_hash": API_HASH, "phone": "+919876543210"},
    )
    assert r.status_code == 200, r.text
    tg = r.json()["telegram"]
    assert tg["api_hash"]["set"] is True
    assert tg["phone"]["hint"].endswith("3210")
    assert API_HASH not in r.text
    assert "9876543210" not in r.text

    engine = create_async_engine(TEST_DB_URL)
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT name, ciphertext FROM secrets"))).all()
    await engine.dispose()
    assert {n for n, _ in rows} >= {"telegram.api_id", "telegram.api_hash", "telegram.phone"}
    assert all(API_HASH.encode() not in bytes(ct) for _, ct in rows)

    assert (await db_client.delete("/api/v1/integrations/telegram")).status_code == 204
    body = (await db_client.get("/api/v1/integrations")).json()
    assert body["telegram"]["api_hash"]["set"] is False


async def test_credential_validation(db_client: AsyncClient) -> None:
    r = await db_client.put("/api/v1/integrations/telegram", json={"phone": "98765"})
    assert r.status_code == 422
    r = await db_client.put("/api/v1/integrations/telegram", json={"api_hash": "xyz"})
    assert r.status_code == 422


async def test_kite_and_llm(db_client: AsyncClient) -> None:
    r = await db_client.put(
        "/api/v1/integrations/kite", json={"api_key": "kitekey1", "api_secret": "s3cr3t!!"}
    )
    k = r.json()["kite"]
    assert k["api_key"]["set"]
    assert k["api_secret"] == {"set": True, "hint": None}
    r = await db_client.put("/api/v1/integrations/llm", json={"api_key": "sk-ant-xxxxxxxx1234"})
    assert r.json()["llm"]["api_key"]["hint"].endswith("1234")


async def test_runtime_settings(db_client: AsyncClient) -> None:
    s = (await db_client.get("/api/v1/settings")).json()
    assert s["trading"]["kill_switch"] is False
    assert s["trading"]["live_armed"] is False

    r = await db_client.patch("/api/v1/settings/trading", json={"kill_switch": True, "bogus": 1})
    assert r.status_code == 200
    assert r.json()["kill_switch"] is True

    r = await db_client.patch("/api/v1/settings/trading", json={"live_armed": True})
    assert r.status_code == 403  # env flag off

    r = await db_client.patch("/api/v1/settings/trading", json={"min_confidence": 2})
    assert r.status_code == 422

    r = await db_client.patch("/api/v1/settings/parsing", json={"mode": "rules_only"})
    assert r.json()["mode"] == "rules_only"
