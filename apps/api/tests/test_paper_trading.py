from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.container import Container
from app.models import Order
from tests.fakes import KITE_CSV, FakeTelegram

pytestmark = pytest.mark.db

CREDS = {
    "api_id": "123456",
    "api_hash": "0123456789abcdef0123456789abcdef",
    "phone": "+919876543210",
}
SIGNAL = "BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140/160"


def ctr(c: AsyncClient) -> Container:
    return c._transport.app.state.container  # type: ignore[attr-defined,no-any-return]


async def setup(c: AsyncClient, auto: bool = True) -> dict[str, Any]:
    container = ctr(c)
    container.telegram.factory = FakeTelegram

    async def fetch(_: object) -> str:
        return KITE_CSV

    container.instruments.fetcher = fetch
    await c.post("/api/v1/instruments/sync", json={"exchanges": ["NSE", "NFO"]})
    await c.put("/api/v1/integrations/telegram", json=CREDS)
    await c.post("/api/v1/telegram/login/start")
    await c.post("/api/v1/telegram/login/code", json={"code": "12345"})
    await c.post("/api/v1/telegram/channels", json={"channel_id": "-1001", "name": "Alpha"})
    await c.patch("/api/v1/settings/trading", json={"auto_execute": auto})
    ce = (await c.get("/api/v1/instruments", params={"q": "NIFTY2610824500CE"})).json()["items"][0]
    acct = (await c.get("/api/v1/portfolio/summary")).json()[0]
    return {"ce": ce, "account": acct["broker_account_id"]}


async def price(c: AsyncClient, inst_id: str, px: str) -> None:
    r = await c.post("/api/v1/market/manual-price", json={"instrument_id": inst_id, "price": px})
    assert r.status_code == 200, r.text


async def push(text: str, mid: str) -> None:
    await FakeTelegram.instances[-1].push("-1001", mid, text)


async def trades(c: AsyncClient) -> list[dict[str, Any]]:
    return list((await c.get("/api/v1/trades")).json()["items"])


async def test_signal_to_target_round_trip(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "1")

    [t] = await trades(c)
    assert t["status"] == "open"
    assert t["quantity"] == 75  # 1 lot (min-lot rule)
    # market 120 + 5 bps slippage = 120.06, rounded up to the 0.05 tick
    assert t["entry_price"] == "120.1000"
    sig = (await c.get("/api/v1/signals")).json()["items"][0]
    assert sig["status"] == "executed"

    orders = (await c.get("/api/v1/orders", params={"trade_plan_id": t["id"]})).json()["items"]
    working = {o["role"]: o for o in orders if o["status"] == "open"}
    assert set(working) == {"stop", "target"}
    assert working["stop"]["order_type"] == "SL-M"
    assert working["stop"]["trigger_price"] == "100.0000"
    assert working["target"]["price"] == "140.0000"

    await price(c, ctx["ce"]["id"], "130")
    t = (await trades(c))[0]
    assert t["status"] == "open"
    assert t["unrealized_pnl"] == "742.5000"  # (130 - 120.10) * 75

    await price(c, ctx["ce"]["id"], "141")
    t = (await trades(c))[0]
    assert t["status"] == "closed"
    assert t["exit_reason"] == "target"
    assert t["exit_price"] == "141.0000"
    assert t["realized_pnl"] == "1527.5000"  # (141 - 120.10) * 75 - 2 x ₹20 charges

    orders = (await c.get("/api/v1/orders", params={"trade_plan_id": t["id"]})).json()["items"]
    stop = next(o for o in orders if o["role"] == "stop")
    assert stop["status"] == "cancelled"  # OCO
    assert (await c.get("/api/v1/portfolio/positions")).json() == []  # flat
    summary = (await c.get("/api/v1/portfolio/summary")).json()[0]
    assert summary["closed_trades"] == 1
    assert summary["win_rate"] == "100.0"

    types = [
        e["event_type"]
        for e in (await c.get("/api/v1/events", params={"limit": 200})).json()["items"]
    ]
    for t_ in ("trade_plan.created", "trade_plan.opened", "trade.executed", "trade_plan.closed"):
        assert t_ in types


async def test_breakout_entry_then_stop(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "110")  # below "ABOVE 120": wait for breakout
    await push(SIGNAL, "2")
    [t] = await trades(c)
    assert t["status"] == "pending"
    entry = (await c.get("/api/v1/orders", params={"trade_plan_id": t["id"]})).json()["items"][0]
    assert entry["order_type"] == "SL-M"
    assert entry["trigger_price"] == "120.0000"

    await price(c, ctx["ce"]["id"], "121")
    assert (await trades(c))[0]["status"] == "open"
    await price(c, ctx["ce"]["id"], "98")
    t = (await trades(c))[0]
    assert t["status"] == "closed"
    assert t["exit_reason"] == "stop"
    assert float(t["realized_pnl"]) < 0
    summary = (await c.get("/api/v1/portfolio/summary")).json()[0]
    assert float(summary["realized_today"]) < 0


async def test_unfilled_entry_expires(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "150")  # already above the range: limit at 120, waits
    await push(SIGNAL, "3")
    [t] = await trades(c)
    assert t["status"] == "pending"
    container = ctr(c)
    async with container.db.session_factory() as s:
        await s.execute(update(Order).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await s.commit()
    await container.engine.tick()
    t = (await trades(c))[0]
    assert t["status"] == "cancelled"
    assert t["exit_reason"] == "expired"


async def test_auto_execute_off_and_manual_execute(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c, auto=False)
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "4")
    assert await trades(c) == []
    sig = (await c.get("/api/v1/signals")).json()["items"][0]
    r = await c.post(f"/api/v1/signals/{sig['id']}/execute")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "open"
    r = await c.post(f"/api/v1/signals/{sig['id']}/execute")
    assert r.status_code == 422
    assert "already executed" in r.json()["error"]["message"]


async def test_kill_switch_and_risk_limits(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "120")
    await c.patch("/api/v1/settings/trading", json={"kill_switch": True})
    await push(SIGNAL, "5")
    assert await trades(c) == []
    skipped = (
        await c.get("/api/v1/events", params={"event_type": "signal.execution_skipped"})
    ).json()
    assert skipped["items"][0]["payload"]["reason"] == "kill switch is on"

    await c.patch("/api/v1/settings/trading", json={"kill_switch": False})
    await c.patch(
        f"/api/v1/broker-accounts/{ctx['account']}", json={"settings": {"max_open_trades": 1}}
    )
    await push(SIGNAL, "6")
    await push("BUY NIFTY 24500 CE ABOVE 121 SL 101 TGT 141", "7")
    assert len(await trades(c)) == 1

    r = await c.patch(
        f"/api/v1/broker-accounts/{ctx['account']}", json={"settings": {"risk_per_trade_pct": 50}}
    )
    assert r.status_code == 422


async def test_short_disallowed_by_default(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "120")
    await push("SELL NIFTY 24500 CE 120 SL 140 TGT 100", "8")
    assert await trades(c) == []
    ev = (await c.get("/api/v1/events", params={"event_type": "signal.execution_skipped"})).json()
    assert "short" in ev["items"][0]["payload"]["reason"]


async def test_manual_close_and_manual_orders(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "9")
    t = (await trades(c))[0]
    await price(c, ctx["ce"]["id"], "125")
    r = await c.post(f"/api/v1/trades/{t['id']}/close")
    assert r.json()["status"] == "closed"
    assert r.json()["exit_reason"] == "manual"
    assert (await c.post(f"/api/v1/trades/{t['id']}/close")).status_code == 422

    body = {
        "instrument_id": ctx["ce"]["id"],
        "side": "BUY",
        "quantity": 75,
        "order_type": "LIMIT",
        "price": "100",
    }
    r = await c.post("/api/v1/orders", json=body)
    assert r.status_code == 201
    assert r.json()["status"] == "open"
    r = await c.post(f"/api/v1/orders/{r.json()['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    r = await c.post("/api/v1/orders", json={**body, "quantity": 10})
    assert r.status_code == 422  # not a lot multiple
    r = await c.post("/api/v1/orders", json={**body, "order_type": "MARKET"})
    assert r.json()["status"] == "filled"
    pos = (await c.get("/api/v1/portfolio/positions")).json()
    assert pos[0]["quantity"] == 75


async def test_no_live_paths(db_client: AsyncClient) -> None:
    r = await db_client.post(
        "/api/v1/broker-accounts", json={"broker": "kite", "label": "real", "mode": "live"}
    )
    assert r.status_code == 403
    r = await db_client.patch("/api/v1/settings/trading", json={"live_armed": True})
    assert r.status_code == 403
