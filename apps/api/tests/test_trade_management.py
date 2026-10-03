"""TP1/TP2 ladders, step and points trailing, editing a running trade, partial
exits, enter-now and the exit-all panic button."""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import ExitMode, Side, TrailMode
from app.services.risk import AccountRiskSettings, TargetLeg, split_targets, step_stop, trail_stop
from tests.test_paper_trading import SIGNAL, price, push, setup, trades

D = Decimal


# ------------------------------------------------------------ pure helpers
def test_split_targets_front_loads_lots() -> None:
    s = AccountRiskSettings()
    legs = split_targets(s, [D(140), D(160)], 150, 75)
    assert [(leg.price, leg.quantity) for leg in legs] == [(D(140), 75), (D(160), 75)]
    legs = split_targets(s, [D(140), D(160)], 225, 75)
    assert [leg.quantity for leg in legs] == [150, 75]
    # one lot: everything at TP1
    assert [leg.quantity for leg in split_targets(s, [D(140), D(160)], 75, 75)] == [75]
    single = AccountRiskSettings(exit_mode=ExitMode.SINGLE, target_index=2)
    assert [(x.price, x.quantity) for x in split_targets(single, [D(140), D(160)], 150, 75)] == [
        (D(160), 150)
    ]
    assert split_targets(s, [], 150, 75) == []


def test_trailing_helpers() -> None:
    # points: long, best 150, trail 10 -> 140 (only ever tightens)
    assert trail_stop(Side.BUY, TrailMode.POINTS, D(10), D(100), D(150), D("0.05")) == D(140)
    assert trail_stop(Side.BUY, TrailMode.POINTS, D(10), D(145), D(150), D("0.05")) is None
    assert trail_stop(Side.SELL, TrailMode.PERCENT, D(10), D(120), D(100), D("0.05")) == D(110)
    assert trail_stop(Side.BUY, TrailMode.STEP, D(10), D(100), D(150), D("0.05")) is None
    legs = [
        TargetLeg(price=D(140), quantity=75, status="hit"),
        TargetLeg(price=D(160), quantity=75),
    ]
    assert step_stop(Side.BUY, D(120), legs, D(100)) == D(120)  # TP1 hit -> cost
    legs[1].status = "hit"
    assert step_stop(Side.BUY, D(120), legs, D(120)) == D(140)  # TP2 hit -> TP1


# ------------------------------------------------------------ engine (DB)
async def two_lots(c: AsyncClient, ctx: dict[str, Any], **extra: object) -> None:
    r = await c.patch(
        f"/api/v1/broker-accounts/{ctx['account']}",
        json={"settings": {"risk_per_trade_pct": 4, **extra}},
    )
    assert r.status_code == 200, r.text


async def orders(c: AsyncClient, plan_id: str) -> list[dict[str, Any]]:
    r = await c.get("/api/v1/orders", params={"trade_plan_id": plan_id})
    return list(r.json()["items"])


@pytest.mark.db
async def test_tp1_then_step_trail_to_cost(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await two_lots(c, ctx)
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "10")  # TGT 140/160

    [t] = await trades(c)
    assert t["quantity"] == 150
    assert t["open_quantity"] == 150
    assert [(x["price"], x["quantity"]) for x in t["targets"]] == [("140", 75), ("160", 75)]
    working = [o for o in await orders(c, t["id"]) if o["status"] == "open"]
    assert sorted((o["role"], o["quantity"]) for o in working) == [
        ("stop", 150),
        ("target", 75),
        ("target", 75),
    ]

    await price(c, ctx["ce"]["id"], "141")  # TP1
    [t] = await trades(c)
    assert t["status"] == "open"
    assert t["open_quantity"] == 75
    assert [x["status"] for x in t["targets"]] == ["hit", "open"]
    assert t["stop_loss"] == t["entry_price"] == "120.1000"  # step: SL to cost
    stop = next(o for o in await orders(c, t["id"]) if o["role"] == "stop")
    assert stop["quantity"] == 75
    assert stop["trigger_price"] == "120.1000"

    await price(c, ctx["ce"]["id"], "119")  # back to cost: rest stopped out at breakeven
    [t] = await trades(c)
    assert t["status"] == "closed"
    assert t["exit_reason"] == "trailing_stop"
    # TP1: (141-120.10)*75 = 1567.5 ; rest: SL-M at 119 - 5bps -> 118.90 => -90 ; 3 fills x ₹20
    assert t["gross_pnl"] == "1477.5000"
    assert t["realized_pnl"] == "1417.5000"
    assert (await c.get("/api/v1/portfolio/positions")).json() == []


@pytest.mark.db
async def test_points_trailing_follows_price(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await c.patch(
        f"/api/v1/broker-accounts/{ctx['account']}",
        json={"settings": {"trail_mode": "points", "trail_value": 8}},
    )
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "11")
    await price(c, ctx["ce"]["id"], "125")
    [t] = await trades(c)
    assert t["stop_loss"] == "117.0000"  # 125 - 8
    await price(c, ctx["ce"]["id"], "122")  # pullback: stop stays
    assert (await trades(c))[0]["stop_loss"] == "117.0000"
    await price(c, ctx["ce"]["id"], "116")
    t = (await trades(c))[0]
    assert t["status"] == "closed"
    assert t["exit_reason"] == "trailing_stop"


@pytest.mark.db
async def test_edit_sl_targets_and_partial_exit(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await two_lots(c, ctx, trail_mode="none")
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "12")
    [t] = await trades(c)

    r = await c.patch(f"/api/v1/trades/{t['id']}", json={"stop_loss": 125})
    assert r.status_code == 422  # above the market
    r = await c.patch(
        f"/api/v1/trades/{t['id']}",
        json={"stop_loss": 110, "targets": [{"price": 150, "quantity": 150}]},
    )
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["stop_loss"] == "110.0000"
    ladder = [(x["price"], x["quantity"], x["status"]) for x in t["targets"]]
    assert ladder == [("150", 150, "open")]
    working = [o for o in await orders(c, t["id"]) if o["status"] == "open"]
    assert sorted((o["role"], o["quantity"]) for o in working) == [("stop", 150), ("target", 150)]
    assert next(o for o in working if o["role"] == "stop")["trigger_price"] == "110.0000"

    r = await c.post(f"/api/v1/trades/{t['id']}/exit", json={"quantity": 50})
    assert r.status_code == 422  # not whole lots
    r = await c.post(f"/api/v1/trades/{t['id']}/exit", json={"quantity": 75})
    t = r.json()
    assert t["status"] == "open"
    assert t["open_quantity"] == 75
    working = [o for o in await orders(c, t["id"]) if o["status"] == "open"]
    assert sorted((o["role"], o["quantity"]) for o in working) == [("stop", 75), ("target", 75)]

    r = await c.post(f"/api/v1/trades/{t['id']}/stop-to-cost")
    assert r.status_code == 422  # price (120) is below cost (120.10)
    await price(c, ctx["ce"]["id"], "125")
    r = await c.post(f"/api/v1/trades/{t['id']}/stop-to-cost")
    assert r.status_code == 200, r.text
    assert r.json()["stop_loss"] == "120.1000"
    r = await c.post(f"/api/v1/trades/{t['id']}/exit")
    t = r.json()
    assert t["status"] == "closed"
    assert t["exit_reason"] == "manual"
    assert t["open_quantity"] == 0


@pytest.mark.db
async def test_enter_now_skips_breakout_wait(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "110")  # below ABOVE 120: waits
    await push(SIGNAL, "13")
    [t] = await trades(c)
    assert t["status"] == "pending"
    r = await c.post(f"/api/v1/trades/{t['id']}/enter-now")
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["status"] == "open"
    assert t["entry_price"] == "110.1000"  # 110 + 5 bps, ticked up
    assert t["stop_loss"] == "100.0000"
    await price(c, ctx["ce"]["id"], "99")
    r = await c.post(f"/api/v1/trades/{t['id']}/enter-now")
    assert r.status_code == 422


@pytest.mark.db
async def test_exit_all_panic_button(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "14")  # opens
    await push("BUY NIFTY 24500 CE ABOVE 130 SL 115 TGT 150", "15")  # waits for 130
    # plus a manual position outside any trade
    await c.post(
        "/api/v1/orders",
        json={"instrument_id": ctx["ce"]["id"], "side": "BUY", "quantity": 75},
    )
    statuses = sorted(t["status"] for t in await trades(c))
    assert statuses == ["open", "pending"]

    r = await c.post("/api/v1/trading/exit-all")
    assert r.status_code == 200, r.text
    assert r.json() == {"cancelled": 1, "exited": 1, "flattened": 1}
    ts = await trades(c)
    assert sorted((t["status"], t["exit_reason"]) for t in ts) == [
        ("cancelled", "exit_all"),
        ("closed", "exit_all"),
    ]
    assert (await c.get("/api/v1/portfolio/positions")).json() == []
    trading = (await c.get("/api/v1/settings")).json()["trading"]
    assert trading["kill_switch"] is True
    # kill switch blocks new entries
    await push("BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140", "16")
    assert len(await trades(c)) == 2
    r = await c.post("/api/v1/trading/kill-switch", json={"on": False})
    assert r.status_code == 204
    assert (await c.get("/api/v1/settings")).json()["trading"]["kill_switch"] is False
