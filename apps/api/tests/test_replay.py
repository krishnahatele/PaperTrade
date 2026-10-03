"""Replay: simulator rules, end-to-end run from Telegram history / stored
messages, the report, CSV, and isolation from live paper trading."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.adapters.history.base import Candle, HistoryAdapter, HistoryUnavailableError
from app.models import Instrument
from app.models.enums import ExitReason, Side, TrailMode
from app.replay.simulator import SameCandle, SimSignal, simulate
from app.services.risk import AccountRiskSettings
from tests.fakes import msg
from tests.test_paper_trading import ctr, setup

D = Decimal
T0 = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)  # 09:30 IST
TICK = D("0.05")


def bars(*ohlc: tuple[float, float, float, float], start: datetime = T0) -> list[Candle]:
    return [
        Candle(
            ts=start + timedelta(minutes=i),
            open=D(str(o)),
            high=D(str(h)),
            low=D(str(lo)),
            close=D(str(c)),
        )
        for i, (o, h, lo, c) in enumerate(ohlc)
    ]


SIG = SimSignal(
    side=Side.BUY,
    entry_low=D(120),
    entry_high=D(120),
    stop_loss=D(100),
    targets=[D(140), D(160)],
    message_at=T0,
)
TWO_LOTS = AccountRiskSettings(risk_per_trade_pct=D(4), slippage_bps=0, charges_per_order=D(20))


def test_breakout_entry_tp1_then_stop_at_cost() -> None:
    candles = bars(
        (110, 115, 108, 114),  # below 120: wait
        (114, 122, 113, 121),  # breakout: buy 150 @ 120
        (121, 142, 120, 141),  # TP1 140 (75) -> SL to cost 120
        (141, 141, 118, 119),  # back to cost: rest stopped
    )
    r = simulate(SIG, candles, TWO_LOTS, 75, TICK, timedelta(minutes=30), None)
    assert r.entered
    assert (r.quantity, r.entry_price, r.entry_at) == (150, D(120), T0 + timedelta(minutes=1))
    assert r.targets_hit == 1
    assert r.exit_reason is ExitReason.TRAILING_STOP
    assert r.gross == D(1500)  # 75 x 20 at TP1, 75 x 0 at cost
    assert r.charges == D(60)
    assert r.net == D(1440)
    assert r.r_multiple == D("0.50")
    assert r.mfe == D(22)


def test_both_targets_and_conservative_same_candle() -> None:
    candles = bars((120, 141, 119, 140), (140, 161, 139, 160))
    r = simulate(SIG, candles, TWO_LOTS, 75, TICK, timedelta(minutes=30), None)
    assert r.exit_reason is ExitReason.TARGET
    assert r.targets_hit == 2
    assert r.gross == D(75 * 20 + 75 * 40)
    # A candle touching both stop and target: stop first by default
    wide = bars((120, 145, 99, 130))
    r = simulate(SIG, wide, TWO_LOTS, 75, TICK, timedelta(minutes=30), None)
    assert r.exit_reason is ExitReason.STOP
    assert r.targets_hit == 0
    r = simulate(
        SIG, wide, TWO_LOTS, 75, TICK, timedelta(minutes=30), None, SameCandle.TARGET_FIRST
    )
    assert r.targets_hit == 1


def test_entry_window_and_square_off_and_points_trailing() -> None:
    late = bars(*[(110, 111, 109, 110)] * 40)
    r = simulate(SIG, late, TWO_LOTS, 75, TICK, timedelta(minutes=30), None)
    assert not r.entered
    assert "never reached" in (r.note or "")

    flat = bars((120, 121, 119, 120), (120, 125, 119, 124), (124, 126, 123, 125))
    r = simulate(SIG, flat, TWO_LOTS, 75, TICK, timedelta(minutes=30), T0 + timedelta(minutes=2))
    assert r.exit_reason is ExitReason.END_OF_DAY
    assert r.exit_at == T0 + timedelta(minutes=2)

    trail = AccountRiskSettings(
        slippage_bps=0, charges_per_order=D(0), trail_mode=TrailMode.POINTS, trail_value=D(5)
    )
    run = bars((120, 121, 119, 120), (120, 130, 120, 129), (129, 129, 124, 125))
    r = simulate(SIG, run, trail, 75, TICK, timedelta(minutes=30), None)
    assert r.exit_reason is ExitReason.TRAILING_STOP  # SL trailed to 125
    assert r.exit_price == D(125)


# ------------------------------------------------------------- end-to-end
class FakeHistory(HistoryAdapter):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []

    async def minute_candles(self, inst: Instrument, day_from: date, day_to: date) -> list[Candle]:
        self.calls.append((inst.tradingsymbol, day_from, day_to))
        if inst.tradingsymbol == "INFY":
            raise HistoryUnavailableError("no data for INFY")
        start = datetime(day_from.year, day_from.month, day_from.day, 3, 45, tzinfo=UTC)
        if inst.tradingsymbol.startswith("NIFTY"):
            # 09:15 IST open 115 -> breakout -> TP1 -> TP2
            return bars(
                (115, 116, 114, 115),
                *[(115, 116, 114, 115)] * 20,
                (116, 122, 116, 121),
                (121, 141, 121, 140),
                (140, 161, 140, 160),
                start=start,
            )
        # RELIANCE: opens in range, then stop
        return bars(*[(2450, 2452, 2445, 2449)] * 10, *[(2446, 2447, 2400, 2405)] * 3, start=start)


@pytest.mark.db
async def test_replay_end_to_end_report_and_isolation(db_client: AsyncClient) -> None:
    c = db_client
    await setup(c)
    container = ctr(c)
    hist = FakeHistory()
    container.history.override = hist
    fake = container.telegram.adapter
    day = date(2026, 9, 1)
    at = datetime(2026, 9, 1, 3, 50, tzinfo=UTC)  # 09:20 IST
    fake.history["-1001"] = [  # type: ignore[attr-defined]
        msg("-1001", "1", "Good morning traders"),
        msg("-1001", "2", "BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140/160"),
        msg("-1001", "3", "BUY RELIANCE 2450 SL 2420 TGT 2500"),
        msg("-1001", "4", "BUY INFY 1500 SL 1480 TGT 1550"),
        msg("-1001", "5", "BUY ZOMATOX 200 SL 190 TGT 220"),
        msg("-1001", "6", "BUY TATAMOTORS FUT 950 TGT 970"),
        msg("-1001", "7", "Target 1 hit"),
    ]
    for i, m in enumerate(fake.history["-1001"]):  # type: ignore[attr-defined]
        m.sent_at = at + timedelta(seconds=i)
    before = {
        k: (await c.get(f"/api/v1/{k}")).json()["total"] for k in ("orders", "trades", "signals")
    }

    r = await c.post(
        "/api/v1/replays",
        json={
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
            "settings": {"risk_per_trade_pct": 4, "slippage_bps": 0},
        },
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "done", run
    rep = run["report"]
    assert rep["messages_scanned"] == 7
    assert rep["message_origin"] == "telegram"
    o = rep["overall"]
    assert (o["signals"], o["traded"], o["wins"], o["losses"]) == (5, 2, 1, 1)
    assert (o["no_data"], o["unresolved"], o["incomplete"]) == (1, 1, 1)
    assert o["win_rate"] == "50.0"
    assert o["accuracy_t1"] == "50.0"
    assert set(rep["by_segment"]) >= {"fno", "equity"}
    assert rep["by_source"]["Alpha"]["signals"] == 5
    assert rep["targets_hit"]["T2"]["count"] == 1
    assert len(rep["equity_curve"]) == 3
    assert rep["data_sources"] == {"fake": 2}
    assert ("NIFTY2610824500CE", day, day) in hist.calls

    trades = (await c.get(f"/api/v1/replays/{run['id']}/trades")).json()
    outcomes = {t["tradingsymbol"]: t["outcome"] for t in trades["items"]}
    assert outcomes == {
        "NIFTY2610824500CE": "win",
        "RELIANCE": "loss",
        "INFY": "no_data",
        "ZOMATOX": "unresolved",
        "TATAMOTORS99JANFUT": "incomplete",
    }
    nifty = next(t for t in trades["items"] if t["outcome"] == "win")
    assert nifty["exit_reason"] == "target"
    assert nifty["targets_hit"] == 2

    csv = await c.get(f"/api/v1/replays/{run['id']}/trades.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0].startswith("message_at,source_name")
    assert len(csv.text.splitlines()) == 6

    # Isolation: live paper trading untouched
    after = {
        k: (await c.get(f"/api/v1/{k}")).json()["total"] for k in ("orders", "trades", "signals")
    }
    assert after == before

    runs = (await c.get("/api/v1/replays")).json()
    assert runs[0]["overall"]["traded"] == 2
    assert (await c.delete(f"/api/v1/replays/{run['id']}")).status_code == 204


@pytest.mark.db
async def test_replay_validation_and_stored_messages(db_client: AsyncClient) -> None:
    c = db_client
    await setup(c)
    container = ctr(c)
    container.history.override = FakeHistory()
    r = await c.post("/api/v1/replays", json={"date_from": "2026-09-10", "date_to": "2026-09-01"})
    assert r.status_code == 422
    r = await c.post("/api/v1/replays", json={"date_from": "2026-01-01", "date_to": "2026-03-01"})
    assert r.status_code == 422
    # Stored messages: what MarketOS received live (here: none in that window)
    r = await c.post(
        "/api/v1/replays",
        json={"date_from": "2026-09-01", "date_to": "2026-09-01", "messages": "stored"},
    )
    assert r.json()["status"] == "done"
    assert r.json()["report"]["messages_scanned"] == 0
