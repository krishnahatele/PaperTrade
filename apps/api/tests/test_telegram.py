import pytest
from httpx import AsyncClient

from app.container import Container
from tests.fakes import FakeTelegram, msg

pytestmark = pytest.mark.db

CREDS = {
    "api_id": "123456",
    "api_hash": "0123456789abcdef0123456789abcdef",
    "phone": "+919876543210",
}


@pytest.fixture
async def tg(db_client: AsyncClient) -> tuple[AsyncClient, Container]:
    container: Container = db_client._transport.app.state.container  # type: ignore[attr-defined]
    container.telegram.factory = FakeTelegram
    FakeTelegram.instances.clear()
    return db_client, container


def latest() -> FakeTelegram:
    return FakeTelegram.instances[-1]


async def login(c: AsyncClient) -> None:
    assert (await c.put("/api/v1/integrations/telegram", json=CREDS)).status_code == 200
    r = await c.post("/api/v1/telegram/login/start")
    assert r.json() == {"step": "code"}
    r = await c.post("/api/v1/telegram/login/code", json={"code": "12345"})
    assert r.json() == {"step": "done"}


async def test_login_requires_credentials(tg: tuple[AsyncClient, Container]) -> None:
    c, _ = tg
    r = await c.post("/api/v1/telegram/login/start")
    assert r.status_code == 403
    st = (await c.get("/api/v1/telegram/status")).json()
    assert st["configured"] is False


async def test_login_flow_stores_encrypted_session(tg: tuple[AsyncClient, Container]) -> None:
    c, container = tg
    await login(c)
    assert latest().code_sent_to == "+919876543210"
    st = (await c.get("/api/v1/telegram/status")).json()
    assert st["authorized"] is True
    integ = (await c.get("/api/v1/integrations")).json()
    assert integ["telegram"]["authorized"] is True
    # Session survives a reload (e.g. API restart) via the encrypted store.
    await container.telegram.reload()
    assert latest().session == "SESSION-OK"
    assert await latest().is_authorized()


async def test_wrong_code_and_2fa(tg: tuple[AsyncClient, Container]) -> None:
    c, _ = tg
    await c.put("/api/v1/integrations/telegram", json=CREDS)
    await c.post("/api/v1/telegram/login/start")
    r = await c.post("/api/v1/telegram/login/code", json={"code": "00000"})
    assert r.status_code == 400
    latest().needs_password = True
    r = await c.post("/api/v1/telegram/login/code", json={"code": "12345"})
    assert r.json() == {"step": "password"}
    r = await c.post("/api/v1/telegram/login/password", json={"password": "nope"})
    assert r.status_code == 400
    r = await c.post("/api/v1/telegram/login/password", json={"password": "2fa-pass"})
    assert r.json() == {"step": "done"}


async def test_channels_ingest_dedupe_and_backfill(tg: tuple[AsyncClient, Container]) -> None:
    c, _ = tg
    await login(c)
    chans = (await c.get("/api/v1/telegram/channels")).json()
    assert [ch["id"] for ch in chans] == ["-1001", "-1002"]
    assert chans[0]["source_id"] is None

    r = await c.post(
        "/api/v1/telegram/channels", json={"channel_id": "-1001", "name": "Alpha Calls"}
    )
    assert r.status_code == 201
    source_id = r.json()["id"]
    fake = latest()
    assert fake.watched == ["-1001"]

    await fake.push("-1001", "10", "BUY INFY 1500 SL 1480 TGT 1550")
    await fake.push("-1001", "10", "BUY INFY 1500 SL 1480 TGT 1550")  # duplicate delivery
    await fake.push("-1002", "11", "not watched")

    msgs = (await c.get(f"/api/v1/signal-sources/{source_id}/messages")).json()
    assert msgs["total"] == 1
    assert msgs["items"][0]["content"].startswith("BUY INFY")
    assert msgs["items"][0]["status"] == "pending"

    events = (await c.get("/api/v1/events", params={"event_type": "raw_message.received"})).json()
    assert events["total"] == 1

    fake.history["-1001"] = [msg("-1001", "9", "older"), msg("-1001", "10", "dup")]
    r = await c.post(f"/api/v1/telegram/sources/{source_id}/backfill", params={"limit": 10})
    assert r.json() == {"stored": 1}

    # Disabling the source stops listening.
    r = await c.patch(f"/api/v1/signal-sources/{source_id}", json={"is_enabled": False})
    assert r.json()["is_enabled"] is False
    assert fake.watched == []

    chans = (await c.get("/api/v1/telegram/channels")).json()
    assert chans[0]["source_id"] == source_id
    assert chans[0]["source_enabled"] is False


async def test_logout_clears_session(tg: tuple[AsyncClient, Container]) -> None:
    c, _ = tg
    await login(c)
    assert (await c.post("/api/v1/telegram/logout")).status_code == 204
    st = (await c.get("/api/v1/telegram/status")).json()
    assert st["authorized"] is False
    integ = (await c.get("/api/v1/integrations")).json()
    assert integ["telegram"]["authorized"] is False
    assert integ["telegram"]["api_id"]["set"] is True  # credentials kept


async def test_delete_source(tg: tuple[AsyncClient, Container]) -> None:
    c, _ = tg
    src = (await c.post("/api/v1/signal-sources", json={"kind": "manual", "name": "X"})).json()
    assert (await c.delete(f"/api/v1/signal-sources/{src['id']}")).status_code == 204
    assert (await c.get(f"/api/v1/signal-sources/{src['id']}")).status_code == 404
