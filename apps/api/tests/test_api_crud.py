import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.db

INFY = {"exchange": "NSE", "tradingsymbol": "INFY", "name": "Infosys", "instrument_type": "EQ"}


async def test_instrument_create_list_get(db_client: AsyncClient) -> None:
    r = await db_client.post("/api/v1/instruments", json=INFY)
    assert r.status_code == 201, r.text
    inst = r.json()
    assert inst["tick_size"] == "0.0500"

    r = await db_client.get("/api/v1/instruments", params={"q": "IN", "exchange": "NSE"})
    assert r.json()["total"] == 1

    r = await db_client.get(f"/api/v1/instruments/{inst['id']}")
    assert r.json()["tradingsymbol"] == "INFY"


async def test_instrument_duplicate_conflicts(db_client: AsyncClient) -> None:
    assert (await db_client.post("/api/v1/instruments", json=INFY)).status_code == 201
    r = await db_client.post("/api/v1/instruments", json=INFY)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_not_found(db_client: AsyncClient) -> None:
    r = await db_client.get(f"/api/v1/instruments/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_validation_error(db_client: AsyncClient) -> None:
    r = await db_client.post("/api/v1/instruments", json={**INFY, "exchange": "NYSE"})
    assert r.status_code == 422


async def test_live_broker_account_rejected(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/broker-accounts", json={"broker": "kite", "label": "real", "mode": "live"}
    )
    assert r.status_code == 403
    r = await db_client.post("/api/v1/broker-accounts", json={"broker": "paper", "label": "sim"})
    assert r.status_code == 201
    assert r.json()["mode"] == "paper"


async def test_manual_signal_flow_and_events(db_client: AsyncClient) -> None:
    src = (
        await db_client.post("/api/v1/signal-sources", json={"kind": "manual", "name": "Desk"})
    ).json()
    inst = (await db_client.post("/api/v1/instruments", json=INFY)).json()

    r = await db_client.post(
        "/api/v1/signals",
        json={
            "source_id": src["id"],
            "instrument_id": inst["id"],
            "symbol_text": "INFY",
            "side": "BUY",
            "entry_low": "1500",
            "entry_high": "1510",
            "stop_loss": "1480",
            "targets": ["1550", "1600"],
        },
    )
    assert r.status_code == 201, r.text
    sig = r.json()
    assert sig["status"] == "new"
    assert sig["parser"] == "manual"
    assert sig["targets"] == ["1550", "1600"]

    r = await db_client.get("/api/v1/signals", params={"status": "new"})
    assert r.json()["total"] == 1

    events = (await db_client.get("/api/v1/events")).json()
    types = {e["event_type"] for e in events["items"]}
    assert {"signal.created", "instrument.created", "signal_source.created"} <= types

    r = await db_client.get("/api/v1/events", params={"aggregate_id": sig["id"]})
    assert r.json()["total"] == 1


async def test_signal_requires_existing_source(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/signals",
        json={"source_id": str(uuid.uuid4()), "symbol_text": "X", "side": "SELL"},
    )
    assert r.status_code == 404


async def test_signal_entry_range_validated(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/signals",
        json={
            "source_id": str(uuid.uuid4()),
            "symbol_text": "X",
            "side": "BUY",
            "entry_low": "10",
            "entry_high": "5",
        },
    )
    assert r.status_code == 422


async def test_read_only_lists(db_client: AsyncClient) -> None:
    for path in ("/api/v1/orders", "/api/v1/positions", "/api/v1/broker-accounts"):
        r = await db_client.get(path)
        assert r.status_code == 200
        assert r.json()["items"] == []
