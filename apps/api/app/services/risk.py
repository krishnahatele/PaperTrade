"""Per-account risk settings and position sizing (pure functions, easy to test)."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from app.models.enums import ExitMode, Side, TrailMode


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
    # How the position is taken off: everything at one target, or split lot-wise
    # across the first N targets (TP1, TP2, ...).
    exit_mode: ExitMode = ExitMode.SPLIT
    target_index: int = Field(
        default=1, ge=1, le=10, description="Single mode: exit everything at target N"
    )
    max_split_targets: int = Field(default=3, ge=1, le=10)
    # Trailing stop-loss: step = SL to cost after TP1, to TP1 after TP2, ...;
    # points / percent = SL follows the best price by that distance.
    trail_mode: TrailMode = TrailMode.STEP
    trail_value: Decimal = Field(default=Decimal("0"), ge=0)
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


class TargetLeg(BaseModel):
    """One take-profit level of a trade: exit ``quantity`` at ``price``."""

    price: Decimal
    quantity: int = Field(gt=0)
    status: str = "open"  # open | hit | cancelled


def split_targets(
    s: AccountRiskSettings, targets: list[Decimal], quantity: int, lot_size: int
) -> list[TargetLeg]:
    """Spread ``quantity`` over the signal's targets according to the account's exit mode.

    Split mode works in whole lots and front-loads: 3 lots over 2 targets is
    2 lots at TP1 and 1 at TP2.
    """
    if not targets or quantity <= 0:
        return []
    lot = max(lot_size, 1)
    lots = max(quantity // lot, 1)
    if s.exit_mode is ExitMode.SINGLE or lots == 1:
        idx = min(s.target_index, len(targets)) - 1 if s.exit_mode is ExitMode.SINGLE else 0
        return [TargetLeg(price=targets[idx], quantity=quantity)]
    n = min(len(targets), lots, s.max_split_targets)
    base, extra = divmod(lots, n)
    legs = [
        TargetLeg(price=targets[i], quantity=(base + (1 if i < extra else 0)) * lot)
        for i in range(n)
    ]
    legs[-1].quantity += quantity - sum(leg.quantity for leg in legs)  # odd (non-lot) remainder
    return legs


def trail_stop(
    side: Side,
    mode: TrailMode,
    value: Decimal,
    stop: Decimal,
    best: Decimal,
    tick: Decimal,
) -> Decimal | None:
    """New (tighter) stop for points/percent trailing, or None if it should not move."""
    if mode not in (TrailMode.POINTS, TrailMode.PERCENT) or value <= 0:
        return None
    dist = value if mode is TrailMode.POINTS else best * value / 100
    if side is Side.BUY:
        cand = round_to_tick(best - dist, tick, Side.SELL)
        return cand if cand > stop else None
    cand = round_to_tick(best + dist, tick, Side.BUY)
    return cand if cand < stop else None


def step_stop(side: Side, entry: Decimal, legs: list[TargetLeg], stop: Decimal) -> Decimal | None:
    """Step trailing after targets hit: TP1 hit -> SL at cost, TP2 hit -> SL at TP1, ..."""
    hit = [leg for leg in legs if leg.status == "hit"]
    if not hit:
        return None
    cand = entry if len(hit) == 1 else hit[-2].price
    better = cand > stop if side is Side.BUY else cand < stop
    return cand if better else None
