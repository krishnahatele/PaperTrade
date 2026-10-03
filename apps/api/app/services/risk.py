"""Per-account risk settings and position sizing (pure functions, easy to test)."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from app.models.enums import Side


class AccountRiskSettings(BaseModel):
    capital: Decimal = Field(default=Decimal("100000"), gt=0)
    risk_per_trade_pct: Decimal = Field(default=Decimal("1"), gt=0, le=10)
    max_position_pct: Decimal = Field(default=Decimal("25"), gt=0, le=100)
    max_open_trades: int = Field(default=5, ge=1, le=100)
    daily_loss_limit_pct: Decimal = Field(default=Decimal("3"), gt=0, le=100)
    auto_execute: bool = True
    allow_short: bool = False
    # If risk-based sizing rounds to zero lots, still take 1 lot when its risk is
    # at most twice the per-trade budget.
    allow_min_lot: bool = True
    target_index: int = Field(default=1, ge=1, le=10, description="Exit at target N (1 = first)")
    entry_tolerance_pct: Decimal = Field(default=Decimal("0.5"), ge=0, le=10)
    slippage_bps: int = Field(default=5, ge=0, le=500)
    charges_per_order: Decimal = Field(default=Decimal("20"), ge=0)


class SizingResult(BaseModel):
    quantity: int
    reason: str | None = None


def size_position(
    s: AccountRiskSettings, entry: Decimal, stop: Decimal, lot_size: int
) -> SizingResult:
    risk_per_unit = abs(entry - stop)
    if risk_per_unit == 0:
        return SizingResult(quantity=0, reason="entry equals stop loss")
    budget = s.capital * s.risk_per_trade_pct / 100
    lot = max(lot_size, 1)
    lots = int((budget / risk_per_unit / lot).to_integral_value(ROUND_DOWN))
    if lots == 0:
        if s.allow_min_lot and risk_per_unit * lot <= budget * 2:
            lots = 1
        else:
            return SizingResult(
                quantity=0,
                reason=f"one lot risks ₹{risk_per_unit * lot:.0f}, over the ₹{budget:.0f} budget",
            )
    cap = s.capital * s.max_position_pct / 100
    max_lots_by_value = int((cap / (entry * lot)).to_integral_value(ROUND_DOWN))
    lots = min(lots, max_lots_by_value)
    if lots == 0:
        return SizingResult(quantity=0, reason="one lot exceeds the max position size")
    return SizingResult(quantity=lots * lot)


def round_to_tick(price: Decimal, tick: Decimal, side: Side | None = None) -> Decimal:
    if tick <= 0:
        return price
    steps = price / tick
    if side is Side.BUY:  # round against us: buy higher, sell lower
        n = steps.to_integral_value(ROUND_CEILING)
    elif side is Side.SELL:
        n = steps.to_integral_value(ROUND_FLOOR)
    else:
        n = steps.to_integral_value(ROUND_HALF_UP)
    return (n * tick).quantize(Decimal("0.0001"))


def apply_fill(
    qty: int, avg: Decimal, realized: Decimal, side: Side, fill_qty: int, price: Decimal
) -> tuple[int, Decimal, Decimal]:
    """Net a fill into a position. Returns (quantity, average_price, realized_pnl)."""
    signed = fill_qty if side is Side.BUY else -fill_qty
    if qty == 0 or (qty > 0) == (signed > 0):
        new_qty = qty + signed
        new_avg = (avg * abs(qty) + price * fill_qty) / abs(new_qty)
        return new_qty, new_avg.quantize(Decimal("0.0001")), realized
    closing = min(fill_qty, abs(qty))
    direction = 1 if qty > 0 else -1
    realized += (price - avg) * closing * direction
    new_qty = qty + signed
    if new_qty == 0:
        return 0, Decimal("0"), realized
    if (new_qty > 0) != (qty > 0):  # flipped through zero
        return new_qty, price, realized
    return new_qty, avg, realized
