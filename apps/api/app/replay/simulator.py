"""Candle-by-candle simulation of one signal, mirroring the live paper engine:

* Entry: inside the call's range -> market at the next candle open; below a
  BUY range -> stop-entry (breakout) at the top of the range; above it -> limit
  at the range (wait for a pullback). Mirrored for SELL. Only within the entry
  window after the message.
* Exits: stop-loss for the open quantity, one target per TP leg, step or
  points/percent trailing, square-off at the session end.
* Intra-candle order is unknown; by default the stop is assumed to hit first
  when a candle touches both (conservative).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from app.adapters.history.base import Candle
from app.models.enums import ExitReason, Side, TrailMode
from app.services.risk import (
    AccountRiskSettings,
    TargetLeg,
    round_to_tick,
    size_position,
    split_targets,
    step_stop,
    trail_stop,
)

ZERO = Decimal("0")


class SameCandle(StrEnum):
    STOP_FIRST = "stop_first"
    TARGET_FIRST = "target_first"


@dataclass
class SimSignal:
    side: Side
    entry_low: Decimal | None
    entry_high: Decimal | None
    stop_loss: Decimal
    targets: list[Decimal]
    message_at: datetime


@dataclass
class Fill:
    at: datetime
    price: Decimal
    quantity: int
    reason: ExitReason | None  # None = entry


@dataclass
class SimResult:
    entered: bool
    note: str | None = None
    quantity: int = 0
    entry_price: Decimal | None = None
    entry_at: datetime | None = None
    exit_price: Decimal | None = None
    exit_at: datetime | None = None
    exit_reason: ExitReason | None = None
    legs: list[TargetLeg] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    gross: Decimal = ZERO
    charges: Decimal = ZERO
    targets_hit: int = 0
    mfe: Decimal = ZERO  # best move for us, per unit
    mae: Decimal = ZERO  # worst move against us, per unit
    initial_risk: Decimal = ZERO  # per unit

    @property
    def net(self) -> Decimal:
        return self.gross - self.charges

    @property
    def r_multiple(self) -> Decimal | None:
        risk = self.initial_risk * self.quantity
        if not self.entered or risk <= 0:
            return None
        return (self.gross / risk).quantize(Decimal("0.01"))


def _slip(price: Decimal, side: Side, bps: int, tick: Decimal) -> Decimal:
    """Market-style fill: worse by ``bps`` for the side doing the trade."""
    s = price * Decimal(bps) / Decimal(10000)
    return round_to_tick(price + s if side is Side.BUY else price - s, tick, side)


def simulate(
    sig: SimSignal,
    candles: list[Candle],
    settings: AccountRiskSettings,
    lot_size: int,
    tick: Decimal,
    entry_window: timedelta,
    square_off_at: datetime | None,
    same_candle: SameCandle = SameCandle.STOP_FIRST,
) -> SimResult:
    buy = sig.side is Side.BUY
    exit_side = Side.SELL if buy else Side.BUY
    # Only candles that start at/after the message (no look-ahead).
    bars = [c for c in candles if c.ts >= sig.message_at]
    if not bars:
        return SimResult(entered=False, note="no candles after the message")

    lo = sig.entry_low or sig.entry_high
    hi = sig.entry_high or sig.entry_low
    first = bars[0]
    ref = (hi if buy else lo) if (lo is not None and hi is not None) else first.open
    sizing = size_position(settings, ref, sig.stop_loss, lot_size)
    if sizing.quantity == 0:
        return SimResult(entered=False, note=sizing.reason or "position size is zero")
    qty = sizing.quantity

    # ---------------------------------------------------------------- entry
    tol = settings.entry_tolerance_pct / 100
    mode = "market"
    if lo is not None and hi is not None:
        if lo * (1 - tol) <= first.open <= hi * (1 + tol):
            mode = "market"
        elif (buy and first.open < lo * (1 - tol)) or (not buy and first.open > hi * (1 + tol)):
            mode = "stop"
        else:
            mode = "limit"
    deadline = sig.message_at + entry_window
    entry_px: Decimal | None = None
    entry_i = 0
    for i, c in enumerate(bars):
        if c.ts > deadline or (square_off_at is not None and c.ts >= square_off_at):
            break
        if mode == "market":
            entry_px = _slip(c.open, sig.side, settings.slippage_bps, tick)
        elif mode == "stop":
            trig = ref
            if (buy and c.high >= trig) or (not buy and c.low <= trig):
                base = max(trig, c.open) if buy else min(trig, c.open)
                entry_px = _slip(base, sig.side, settings.slippage_bps, tick)
        else:  # limit
            if (buy and c.low <= ref) or (not buy and c.high >= ref):
                entry_px = min(ref, c.open) if buy else max(ref, c.open)
        if entry_px is not None:
            entry_i = i
            break
    if entry_px is None:
        return SimResult(entered=False, note="price never reached the entry in time", quantity=qty)
    if (buy and entry_px <= sig.stop_loss) or (not buy and entry_px >= sig.stop_loss):
        return SimResult(entered=False, note="opened beyond the stop-loss", quantity=qty)

    res = SimResult(
        entered=True,
        quantity=qty,
        entry_price=entry_px,
        entry_at=bars[entry_i].ts,
        initial_risk=abs(entry_px - sig.stop_loss),
    )
    res.fills.append(Fill(bars[entry_i].ts, entry_px, qty, None))
    res.charges += settings.charges_per_order
    legs = split_targets(settings, sig.targets, qty, lot_size)
    stop = sig.stop_loss
    open_qty = qty
    best = entry_px
    d = 1 if buy else -1

    def exit_fill(at: datetime, px: Decimal, q: int, reason: ExitReason) -> None:
        nonlocal open_qty
        res.fills.append(Fill(at, px, q, reason))
        res.gross += (px - entry_px) * q * d
        res.charges += settings.charges_per_order
        open_qty -= q
        res.exit_at = at
        res.exit_reason = reason

    def check_stop(c: Candle) -> bool:
        hit = c.low <= stop if buy else c.high >= stop
        if hit:
            base = min(stop, c.open) if buy else max(stop, c.open)
            moved = (stop - sig.stop_loss) * d > 0
            reason = ExitReason.TRAILING_STOP if moved else ExitReason.STOP
            exit_fill(c.ts, _slip(base, exit_side, settings.slippage_bps, tick), open_qty, reason)
        return hit

    def check_targets(c: Candle) -> None:
        nonlocal stop
        for leg in legs:
            if leg.status != "open" or open_qty <= 0:
                continue
            if (buy and c.high >= leg.price) or (not buy and c.low <= leg.price):
                px = max(leg.price, c.open) if buy else min(leg.price, c.open)
                q = min(leg.quantity, open_qty)
                leg.status = "hit"
                res.targets_hit += 1
                exit_fill(c.ts, px, q, ExitReason.TARGET)
                if settings.trail_mode is TrailMode.STEP:
                    new = step_stop(sig.side, entry_px, legs, stop)
                    if new is not None:
                        stop = new

    for c in bars[entry_i:]:
        if square_off_at is not None and c.ts >= square_off_at:
            exit_fill(
                c.ts,
                _slip(c.open, exit_side, settings.slippage_bps, tick),
                open_qty,
                ExitReason.END_OF_DAY,
            )
            break
        res.mfe = max(res.mfe, (c.high - entry_px) if buy else (entry_px - c.low))
        res.mae = max(res.mae, (entry_px - c.low) if buy else (c.high - entry_px))
        if same_candle is SameCandle.STOP_FIRST:
            if check_stop(c):
                break
            check_targets(c)
        else:
            check_targets(c)
            if open_qty > 0 and check_stop(c):
                break
        if open_qty <= 0:
            break
        best = max(best, c.high) if buy else min(best, c.low)
        new = trail_stop(sig.side, settings.trail_mode, settings.trail_value, stop, best, tick)
        if new is not None:
            stop = new
    if open_qty > 0:
        last = bars[-1]
        exit_fill(last.ts, last.close, open_qty, ExitReason.END_OF_DAY)
    for leg in legs:
        if leg.status == "open":
            leg.status = "cancelled"
    res.legs = legs
    exits = [f for f in res.fills if f.reason is not None]
    total = sum(f.quantity for f in exits)
    if total:
        value = sum((f.price * f.quantity for f in exits), ZERO)
        res.exit_price = (value / Decimal(total)).quantize(Decimal("0.0001"))
    if res.targets_hit and all(f.reason is ExitReason.TARGET for f in exits):
        res.exit_reason = ExitReason.TARGET
    return res
