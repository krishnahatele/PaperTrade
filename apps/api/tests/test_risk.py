from decimal import Decimal

from app.models import Order
from app.models.enums import OrderType, Side
from app.services.risk import AccountRiskSettings, apply_fill, round_to_tick, size_position
from app.services.trading import fill_price

S = AccountRiskSettings()  # capital 1,00,000, risk 1% = ₹1000


def test_risk_based_sizing_equity() -> None:
    # 1000 / 30 = 33 shares, but max position 25% = 25000 / 2450 = 10 shares
    assert size_position(S, Decimal("2450"), Decimal("2420"), 1).quantity == 10


def test_sizing_rounds_to_lots_and_min_lot() -> None:
    # 1000/20 = 50 units < 75 lot; one lot risks 1500 <= 2x budget -> 1 lot
    assert size_position(S, Decimal("120"), Decimal("100"), 75).quantity == 75
    strict = S.model_copy(update={"allow_min_lot": False})
    r = size_position(strict, Decimal("120"), Decimal("100"), 75)
    assert r.quantity == 0
    assert "budget" in (r.reason or "")
    # one lot risking more than 2x budget is refused even with allow_min_lot
    assert size_position(S, Decimal("300"), Decimal("200"), 75).quantity == 0


def test_zero_risk_rejected() -> None:
    assert size_position(S, Decimal("100"), Decimal("100"), 1).quantity == 0


def test_round_to_tick() -> None:
    assert round_to_tick(Decimal("120.03"), Decimal("0.05"), Side.BUY) == Decimal("120.05")
    assert round_to_tick(Decimal("120.03"), Decimal("0.05"), Side.SELL) == Decimal("120.00")


def test_apply_fill_netting() -> None:
    q, avg, r = apply_fill(0, Decimal(0), Decimal(0), Side.BUY, 10, Decimal("100"))
    q, avg, r = apply_fill(q, avg, r, Side.BUY, 10, Decimal("110"))
    assert (q, avg) == (20, Decimal("105"))
    q, avg, r = apply_fill(q, avg, r, Side.SELL, 5, Decimal("120"))
    assert (q, avg, r) == (15, Decimal("105"), Decimal("75"))
    q, avg, r = apply_fill(q, avg, r, Side.SELL, 20, Decimal("100"))  # flip short
    assert (q, avg, r) == (-5, Decimal("100"), Decimal("0"))


def _o(side: Side, t: OrderType, price: str | None = None, trig: str | None = None) -> Order:
    return Order(
        side=side,
        order_type=t,
        price=Decimal(price) if price else None,
        trigger_price=Decimal(trig) if trig else None,
        quantity=1,
        filled_quantity=0,
    )


def test_fill_rules() -> None:
    tick = Decimal("0.05")
    assert fill_price(_o(Side.BUY, OrderType.MARKET), Decimal("100"), 10, tick) == Decimal("100.10")
    assert fill_price(_o(Side.BUY, OrderType.LIMIT, "99"), Decimal("100"), 0, tick) is None
    assert fill_price(_o(Side.BUY, OrderType.LIMIT, "101"), Decimal("100"), 0, tick) == Decimal(
        "100"
    )
    assert fill_price(_o(Side.SELL, OrderType.LIMIT, "140"), Decimal("141"), 0, tick) == Decimal(
        "141"
    )
    # stop-loss for a long: SELL SL-M triggers when price falls to trigger
    assert fill_price(_o(Side.SELL, OrderType.SL_M, trig="100"), Decimal("101"), 0, tick) is None
    assert fill_price(
        _o(Side.SELL, OrderType.SL_M, trig="100"), Decimal("99.5"), 0, tick
    ) == Decimal("99.50")
    # breakout entry: BUY SL-M triggers when price rises to trigger
    assert fill_price(_o(Side.BUY, OrderType.SL_M, trig="120"), Decimal("119"), 0, tick) is None
    assert fill_price(
        _o(Side.BUY, OrderType.SL_M, trig="120"), Decimal("120.2"), 0, tick
    ) == Decimal("120.20")
