"""Order management and the paper-trading engine.

* ``execute_signal`` turns a validated signal into a *trade plan*: risk checks,
  position sizing, and an entry order.
* ``tick`` (every ~2 s in the background) matches working paper orders against
  last-traded prices, books fills into positions, and manages each plan's
  exits: once the entry fills, a stop-loss (SL-M) for the open quantity and one
  LIMIT order per take-profit leg (TP1, TP2, ...) are placed. A target fill
  reduces the open quantity (the stop shrinks with it and, with step trailing,
  moves to cost / the previous target); a stop fill closes what is left.
  Points/percent trailing moves the stop as the best price improves.
* ``update_plan`` / ``exit_plan`` / ``enter_now`` / ``exit_all`` are the manual
  controls used by the portal and the Telegram bot.

Live (real-money) accounts are refused here; see ``docs/architecture.md``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import FeatureDisabledError, InvalidInputError, NotFoundError
from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.models import BrokerAccount, Instrument, Order, Position, Signal, Trade, TradePlan
from app.models.enums import (
    BrokerName,
    ExecutionMode,
    ExitReason,
    InstrumentType,
    OrderRole,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    SignalStatus,
    TradePlanStatus,
    TrailMode,
)
from app.services.market_data import MarketDataService
from app.services.risk import (
    AccountRiskSettings,
    TargetLeg,
    apply_fill,
    round_to_tick,
    size_position,
    split_targets,
    step_stop,
    trail_stop,
)
from app.services.runtime import RuntimeStore, TradingRuntime

log = get_logger("marketos.trading")
IST = ZoneInfo("Asia/Kolkata")
WORKING = (OrderStatus.OPEN, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
EXIT_ROLES = (OrderRole.STOP, OrderRole.TARGET, OrderRole.EXIT)
PAPER_ACCOUNT_LABEL = "Paper"


class SkipError(Exception):
    """A signal was deliberately not executed (risk rule, duplicate, ...)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


T = TypeVar("T")


def _req(value: T | None, what: str) -> T:
    if value is None:
        raise NotFoundError(f"{what} not found")
    return value


def _opposite(side: Side) -> Side:
    return Side.SELL if side is Side.BUY else Side.BUY


def legs_of(plan: TradePlan) -> list[TargetLeg]:
    return [TargetLeg.model_validate(x) for x in plan.targets or []]


def _set_legs(plan: TradePlan, legs: list[TargetLeg]) -> None:
    plan.targets = [leg.model_dump(mode="json") for leg in legs]
    open_legs = [leg for leg in legs if leg.status != "cancelled"]
    plan.target = open_legs[0].price if open_legs else None


def _direction(side: Side) -> int:
    return 1 if side is Side.BUY else -1


def _product_for(inst: Instrument) -> ProductType:
    return ProductType.CNC if inst.instrument_type is InstrumentType.EQ else ProductType.NRML


def fill_price(order: Order, ltp: Decimal, slippage_bps: int, tick: Decimal) -> Decimal | None:
    """Price at which a working paper order fills at this LTP, or None."""
    buy = order.side is Side.BUY
    slip = ltp * Decimal(slippage_bps) / Decimal(10000)
    market = round_to_tick(ltp + slip if buy else ltp - slip, tick, order.side)
    if order.order_type is OrderType.MARKET:
        return market
    if order.order_type is OrderType.LIMIT:
        if order.price is None:
            return None
        if (buy and ltp <= order.price) or (not buy and ltp >= order.price):
            return ltp  # marketable: fill at the (better or equal) traded price
        return None
    trigger = order.trigger_price
    if trigger is None:
        return None
    triggered = ltp >= trigger if buy else ltp <= trigger
    if not triggered:
        return None
    if order.order_type is OrderType.SL_M:
        return market
    # SL (stop-limit): after trigger, fill only within the limit
    if order.price is None:
        return None
    if (buy and ltp <= order.price) or (not buy and ltp >= order.price):
        return ltp
    return None


class TradingEngine:
    TICK_SECONDS = 2.0

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        runtime: RuntimeStore,
        market: MarketDataService,
        spawn: Callable[[Awaitable[None], str], None] | None = None,
    ) -> None:
        self.sf = session_factory
        self.bus = bus
        self.runtime = runtime
        self.market = market
        self.spawn = spawn
        self.lock = asyncio.Lock()
        self._pending_events: list[Event] = []

    # ------------------------------------------------------------------ setup
    async def ensure_paper_account(self) -> BrokerAccount:
        async with self.sf() as s:
            acct = await s.scalar(
                select(BrokerAccount).where(
                    BrokerAccount.broker == BrokerName.PAPER,
                    BrokerAccount.label == PAPER_ACCOUNT_LABEL,
                )
            )
            if acct is None:
                acct = BrokerAccount(
                    broker=BrokerName.PAPER,
                    label=PAPER_ACCOUNT_LABEL,
                    mode=ExecutionMode.PAPER,
                    settings=AccountRiskSettings().model_dump(mode="json"),
                )
                s.add(acct)
                await s.commit()
                await s.refresh(acct)
            return acct

    # ------------------------------------------------------------ signal hook
    async def on_signal_event(self, event: Event) -> None:
        if event.aggregate_id is None:
            return
        status = event.payload.get("status") or event.payload.get("to")
        if status != SignalStatus.VALIDATED:
            return
        if not (await self.runtime.get(TradingRuntime)).auto_execute:
            return
        signal_id = event.aggregate_id

        async def run() -> None:
            await self.auto_execute(signal_id, cause=event)

        if self.spawn is None:
            await run()
        else:
            self.spawn(run(), f"execute:{signal_id}")

    async def auto_execute(self, signal_id: uuid.UUID, cause: Event | None = None) -> None:
        async with self.sf() as s:
            accounts = list(
                await s.scalars(
                    select(BrokerAccount).where(
                        BrokerAccount.is_active.is_(True),
                        BrokerAccount.mode == ExecutionMode.PAPER,
                    )
                )
            )
        for acct in accounts:
            if not AccountRiskSettings.model_validate(acct.settings).auto_execute:
                continue
            try:
                await self.execute_signal(signal_id, acct.id, cause=cause)
            except SkipError as exc:
                await self._publish(
                    _event(
                        cause,
                        EventType.SIGNAL_EXECUTION_SKIPPED,
                        "signal",
                        signal_id,
                        {"account": acct.label, "reason": exc.reason},
                    )
                )
                log.info("trading.signal_skipped", signal=str(signal_id), reason=exc.reason)

    # ---------------------------------------------------------- execution
    async def execute_signal(
        self, signal_id: uuid.UUID, account_id: uuid.UUID, cause: Event | None = None
    ) -> TradePlan:
        trading = await self.runtime.get(TradingRuntime)
        if trading.kill_switch:
            raise SkipError("kill switch is on")
        async with self.lock, self.sf() as s:
            sig = await s.get(Signal, signal_id)
            acct = await s.get(BrokerAccount, account_id)
            if sig is None or acct is None:
                raise NotFoundError("Signal or account not found")
            if acct.mode is not ExecutionMode.PAPER:
                raise FeatureDisabledError("Live accounts are not enabled in this build.")
            if not acct.is_active:
                raise SkipError("account is inactive")
            if sig.status not in (SignalStatus.VALIDATED, SignalStatus.EXECUTED):
                raise SkipError(f"signal is {sig.status}, not validated")
            if sig.instrument_id is None or sig.stop_loss is None:
                raise SkipError("signal needs an instrument and a stop loss")
            if datetime.now(UTC) - sig.created_at > timedelta(minutes=trading.signal_ttl_minutes):
                raise SkipError("signal is older than the expiry window")
            dup = await s.scalar(
                select(func.count()).where(
                    TradePlan.signal_id == sig.id, TradePlan.broker_account_id == acct.id
                )
            )
            if dup:
                raise SkipError("already executed on this account")
            settings = AccountRiskSettings.model_validate(acct.settings)
            if sig.side is Side.SELL and not settings.allow_short:
                raise SkipError("short selling is disabled for this account")
            open_plans = await s.scalar(
                select(func.count()).where(
                    TradePlan.broker_account_id == acct.id,
                    TradePlan.status.in_([TradePlanStatus.PENDING, TradePlanStatus.OPEN]),
                )
            )
            if (open_plans or 0) >= settings.max_open_trades:
                raise SkipError(f"max open trades ({settings.max_open_trades}) reached")
            today_pnl = await self.realized_today(s, acct.id)
            if today_pnl <= -(settings.capital * settings.daily_loss_limit_pct / 100):
                raise SkipError("daily loss limit reached")

            inst = _req(await s.get(Instrument, sig.instrument_id), "Instrument")
            ltp = (await self.market.ltp([inst])).get(inst.id)
            entry_lo = sig.entry_low or sig.entry_high
            entry_hi = sig.entry_high or sig.entry_low
            ref = entry_hi if sig.side is Side.BUY else entry_lo
            if ref is None:
                if ltp is None:
                    raise SkipError("no entry price and no live price")
                ref = ltp
            sizing = size_position(settings, ref, sig.stop_loss, inst.lot_size)
            if sizing.quantity == 0:
                raise SkipError(sizing.reason or "position size is zero")

            targets = [Decimal(t) for t in sig.targets]
            legs = split_targets(settings, targets, sizing.quantity, inst.lot_size)
            plan = TradePlan(
                signal_id=sig.id,
                broker_account_id=acct.id,
                instrument_id=inst.id,
                side=sig.side,
                product=_product_for(inst),
                quantity=sizing.quantity,
                planned_entry=ref,
                stop_loss=sig.stop_loss,
                initial_stop_loss=sig.stop_loss,
                trailing={"mode": settings.trail_mode.value, "value": str(settings.trail_value)},
                open_quantity=0,
                status=TradePlanStatus.PENDING,
            )
            _set_legs(plan, legs)
            s.add(plan)
            await s.flush()

            # Entry style from where the market is relative to the call:
            #   inside the range -> MARKET; price hasn't reached it -> stop-entry
            #   (breakout "BUY ABOVE"); price already beyond it -> LIMIT (wait for pullback)
            tol = settings.entry_tolerance_pct / 100
            order_type = OrderType.LIMIT
            price: Decimal | None = ref
            trigger: Decimal | None = None
            if ltp is not None and entry_lo is not None and entry_hi is not None:
                lo, hi = entry_lo * (1 - tol), entry_hi * (1 + tol)
                if lo <= ltp <= hi:
                    order_type, price = OrderType.MARKET, None
                elif (sig.side is Side.BUY and ltp < lo) or (sig.side is Side.SELL and ltp > hi):
                    order_type, price, trigger = OrderType.SL_M, None, ref
            expires = datetime.now(UTC) + timedelta(minutes=trading.signal_ttl_minutes)
            await self._new_order(
                s,
                acct,
                inst,
                plan,
                sig.side,
                sizing.quantity,
                order_type,
                price,
                trigger,
                OrderRole.ENTRY,
                signal_id=sig.id,
                expires_at=expires,
                cause=cause,
            )
            if sig.status is not SignalStatus.EXECUTED:
                sig.status = SignalStatus.EXECUTED
                self._queue(
                    _event(
                        cause,
                        EventType.SIGNAL_STATUS_CHANGED,
                        "signal",
                        sig.id,
                        {
                            "from": SignalStatus.VALIDATED,
                            "to": SignalStatus.EXECUTED,
                            "by": "engine",
                        },
                    )
                )
            self._queue(
                _event(
                    cause,
                    EventType.TRADE_PLAN_CREATED,
                    "trade_plan",
                    plan.id,
                    {
                        "symbol": inst.tradingsymbol,
                        "side": plan.side,
                        "quantity": plan.quantity,
                        "entry": str(ref),
                        "stop": str(plan.stop_loss),
                        "target": str(plan.target) if plan.target else None,
                        "targets": [f"{leg.quantity}@{leg.price}" for leg in legs],
                        "entry_type": order_type,
                    },
                )
            )
            await s.commit()
            await s.refresh(plan)
        await self._flush_events()
        await self.tick()  # fill immediately if the price allows
        async with self.sf() as s:
            return _req(await s.get(TradePlan, plan.id), "Trade")

    async def place_manual_order(
        self,
        account_id: uuid.UUID,
        instrument_id: uuid.UUID,
        side: Side,
        quantity: int,
        order_type: OrderType,
        price: Decimal | None,
        trigger_price: Decimal | None,
    ) -> Order:
        if (await self.runtime.get(TradingRuntime)).kill_switch:
            raise InvalidInputError("Kill switch is on.")
        async with self.lock, self.sf() as s:
            acct = await s.get(BrokerAccount, account_id)
            inst = await s.get(Instrument, instrument_id)
            if acct is None or inst is None:
                raise NotFoundError("Account or instrument not found")
            if acct.mode is not ExecutionMode.PAPER:
                raise FeatureDisabledError("Live accounts are not enabled in this build.")
            if quantity % max(inst.lot_size, 1):
                raise InvalidInputError(
                    f"Quantity must be a multiple of the lot size ({inst.lot_size})."
                )
            if order_type in (OrderType.LIMIT, OrderType.SL) and price is None:
                raise InvalidInputError("Limit orders need a price.")
            if order_type in (OrderType.SL, OrderType.SL_M) and trigger_price is None:
                raise InvalidInputError("Stop orders need a trigger price.")
            order = await self._new_order(
                s,
                acct,
                inst,
                None,
                side,
                quantity,
                order_type,
                price,
                trigger_price,
                OrderRole.MANUAL,
            )
            await s.commit()
            await s.refresh(order)
        await self._flush_events()
        await self.tick()
        async with self.sf() as s:
            return _req(await s.get(Order, order.id), "Order")

    async def cancel_order(self, order_id: uuid.UUID) -> Order:
        async with self.lock, self.sf() as s:
            order = await s.get(Order, order_id)
            if order is None:
                raise NotFoundError("Order not found")
            if order.status not in WORKING:
                raise InvalidInputError(f"Order is already {order.status}.")
            if order.role in (OrderRole.STOP, OrderRole.TARGET):
                raise InvalidInputError(
                    "Bracket orders are managed by their trade; close the trade instead."
                )
            self._set_status(order, OrderStatus.CANCELLED, "cancelled by user")
            if order.trade_plan_id and order.role is OrderRole.ENTRY:
                plan = await s.get(TradePlan, order.trade_plan_id)
                if plan and plan.status is TradePlanStatus.PENDING:
                    self._close_plan(plan, ExitReason.CANCELLED, TradePlanStatus.CANCELLED)
            await s.commit()
            await s.refresh(order)
        await self._flush_events()
        return order

    async def close_plan(self, plan_id: uuid.UUID) -> TradePlan:
        """Cancel a pending trade, or exit an open one completely at market."""
        return await self.exit_plan(plan_id, None)

    async def exit_plan(
        self, plan_id: uuid.UUID, quantity: int | None, reason: ExitReason = ExitReason.MANUAL
    ) -> TradePlan:
        """Exit ``quantity`` (whole lots) of an open trade at market; None = everything."""
        async with self.lock, self.sf() as s:
            plan = await s.get(TradePlan, plan_id)
            if plan is None:
                raise NotFoundError("Trade not found")
            await self._exit_plan(s, plan, quantity, reason)
            await s.commit()
        await self._flush_events()
        await self.tick()
        async with self.sf() as s:
            return _req(await s.get(TradePlan, plan_id), "Trade")

    async def _exit_plan(
        self, s: AsyncSession, plan: TradePlan, quantity: int | None, reason: ExitReason
    ) -> None:
        orders = await self._plan_orders(s, plan.id)
        if plan.status is TradePlanStatus.PENDING:
            if quantity is not None:
                raise InvalidInputError("The entry has not filled yet; cancel the trade instead.")
            for o in orders:
                if o.status in WORKING:
                    self._set_status(o, OrderStatus.CANCELLED, "trade cancelled")
            self._close_plan(
                plan,
                ExitReason.EXIT_ALL if reason is ExitReason.EXIT_ALL else ExitReason.CANCELLED,
                TradePlanStatus.CANCELLED,
            )
            return
        if plan.status is not TradePlanStatus.OPEN:
            raise InvalidInputError(f"Trade is already {plan.status}.")
        if any(o.role is OrderRole.EXIT and o.status in WORKING for o in orders):
            raise InvalidInputError("An exit order is already working.")
        inst = _req(await s.get(Instrument, plan.instrument_id), "Instrument")
        full = quantity is None or quantity >= plan.open_quantity
        qty = plan.open_quantity if full or quantity is None else quantity
        if qty <= 0:
            raise InvalidInputError("Quantity must be positive.")
        if not full and qty % max(inst.lot_size, 1):
            raise InvalidInputError(f"Quantity must be whole lots ({inst.lot_size} per lot).")
        if full:
            for o in orders:
                if o.role in (OrderRole.STOP, OrderRole.TARGET) and o.status in WORKING:
                    self._set_status(o, OrderStatus.CANCELLED, "manual exit")
        acct = _req(await s.get(BrokerAccount, plan.broker_account_id), "Account")
        order = await self._new_order(
            s,
            acct,
            inst,
            plan,
            _opposite(plan.side),
            qty,
            OrderType.MARKET,
            None,
            None,
            OrderRole.EXIT,
        )
        order.status_message = reason.value

    async def enter_now(self, plan_id: uuid.UUID) -> TradePlan:
        """Skip waiting for the signal's entry level: buy/sell now at market."""
        if (await self.runtime.get(TradingRuntime)).kill_switch:
            raise InvalidInputError("Kill switch is on.")
        async with self.lock, self.sf() as s:
            plan = await s.get(TradePlan, plan_id)
            if plan is None:
                raise NotFoundError("Trade not found")
            if plan.status is not TradePlanStatus.PENDING:
                raise InvalidInputError(
                    f"Trade is {plan.status}; only waiting trades can enter now."
                )
            inst = _req(await s.get(Instrument, plan.instrument_id), "Instrument")
            ltp = (await self.market.ltp([inst])).get(inst.id)
            if ltp is None:
                raise InvalidInputError("No live price for this instrument right now.")
            if (plan.side is Side.BUY and ltp <= plan.stop_loss) or (
                plan.side is Side.SELL and ltp >= plan.stop_loss
            ):
                raise InvalidInputError(
                    f"Price {ltp} is already past the stop-loss {plan.stop_loss}."
                )
            for o in await self._plan_orders(s, plan.id):
                if o.role is OrderRole.ENTRY and o.status in WORKING:
                    self._set_status(o, OrderStatus.CANCELLED, "replaced by enter-now")
            acct = _req(await s.get(BrokerAccount, plan.broker_account_id), "Account")
            await self._new_order(
                s,
                acct,
                inst,
                plan,
                plan.side,
                plan.quantity,
                OrderType.MARKET,
                None,
                None,
                OrderRole.ENTRY,
            )
            await s.commit()
        await self._flush_events()
        await self.tick()
        async with self.sf() as s:
            return _req(await s.get(TradePlan, plan_id), "Trade")

    async def update_plan(
        self,
        plan_id: uuid.UUID,
        *,
        stop_loss: Decimal | None = None,
        targets: list[TargetLeg] | None = None,
        trail_mode: TrailMode | None = None,
        trail_value: Decimal | None = None,
        by: str = "user",
    ) -> TradePlan:
        """Change a trade's stop-loss, take-profit ladder or trailing while it runs."""
        async with self.lock, self.sf() as s:
            plan = await s.get(TradePlan, plan_id)
            if plan is None:
                raise NotFoundError("Trade not found")
            if plan.status not in (TradePlanStatus.PENDING, TradePlanStatus.OPEN):
                raise InvalidInputError(f"Trade is already {plan.status}.")
            inst = _req(await s.get(Instrument, plan.instrument_id), "Instrument")
            changes: dict[str, object] = {"by": by}
            if trail_mode is not None or trail_value is not None:
                tr = dict(plan.trailing or {})
                if trail_mode is not None:
                    tr["mode"] = trail_mode.value
                if trail_value is not None:
                    tr["value"] = str(trail_value)
                plan.trailing = tr
                changes["trailing"] = tr
            if stop_loss is not None:
                stop_loss = round_to_tick(stop_loss, inst.tick_size)
                if plan.status is TradePlanStatus.OPEN:
                    ltp = (await self.market.ltp([inst])).get(inst.id)
                    if ltp is not None and (
                        (plan.side is Side.BUY and stop_loss >= ltp)
                        or (plan.side is Side.SELL and stop_loss <= ltp)
                    ):
                        raise InvalidInputError(
                            f"Stop-loss {stop_loss} is past the current price {ltp}; "
                            "use Exit instead."
                        )
                else:
                    ref = plan.planned_entry
                    if ref is not None and (
                        (plan.side is Side.BUY and stop_loss >= ref)
                        or (plan.side is Side.SELL and stop_loss <= ref)
                    ):
                        raise InvalidInputError("Stop-loss must be on the losing side of entry.")
                await self._move_stop(s, plan, stop_loss, by)
                changes["stop"] = str(stop_loss)
            if targets is not None:
                await self._replace_targets(s, plan, inst, targets)
                changes["targets"] = [f"{t.quantity}@{t.price}" for t in legs_of(plan)]
            self._queue(
                Event(
                    type=EventType.TRADE_PLAN_UPDATED,
                    aggregate_type="trade_plan",
                    aggregate_id=plan.id,
                    payload={"symbol": inst.tradingsymbol, **changes},
                )
            )
            await s.commit()
        await self._flush_events()
        await self.tick()
        async with self.sf() as s:
            return _req(await s.get(TradePlan, plan_id), "Trade")

    async def _replace_targets(
        self, s: AsyncSession, plan: TradePlan, inst: Instrument, new: list[TargetLeg]
    ) -> None:
        lot = max(inst.lot_size, 1)
        d = _direction(plan.side)
        ref = plan.entry_price or plan.planned_entry
        for leg in new:
            if leg.quantity % lot:
                raise InvalidInputError(f"Target quantities must be whole lots ({lot} per lot).")
            if ref is not None and (leg.price - ref) * d <= 0:
                raise InvalidInputError(f"Target {leg.price} is not on the profit side of {ref}.")
        old = legs_of(plan)
        kept = [leg for leg in old if leg.status == "hit"]
        avail = plan.quantity if plan.status is TradePlanStatus.PENDING else plan.open_quantity
        if sum(leg.quantity for leg in new) > avail:
            raise InvalidInputError(f"Targets add up to more than the open quantity ({avail}).")
        for o in await self._plan_orders(s, plan.id):
            if o.role is OrderRole.TARGET and o.status in WORKING:
                self._set_status(o, OrderStatus.CANCELLED, "targets changed")
        legs = kept + [TargetLeg(price=leg.price, quantity=leg.quantity) for leg in new]
        _set_legs(plan, legs)
        if plan.status is TradePlanStatus.OPEN:
            acct = _req(await s.get(BrokerAccount, plan.broker_account_id), "Account")
            for i, leg in enumerate(legs):
                if leg.status == "open":
                    o = await self._new_order(
                        s,
                        acct,
                        inst,
                        plan,
                        _opposite(plan.side),
                        leg.quantity,
                        OrderType.LIMIT,
                        leg.price,
                        None,
                        OrderRole.TARGET,
                    )
                    o.leg = i

    async def _move_stop(self, s: AsyncSession, plan: TradePlan, stop: Decimal, by: str) -> None:
        old = plan.stop_loss
        plan.stop_loss = stop
        for o in await self._plan_orders(s, plan.id):
            if o.role is OrderRole.STOP and o.status in WORKING:
                self._modify(o, trigger=stop)
        if by != "user":  # user edits publish one combined update event
            self._queue(
                Event(
                    type=EventType.TRADE_PLAN_UPDATED,
                    aggregate_type="trade_plan",
                    aggregate_id=plan.id,
                    payload={"stop": str(stop), "from": str(old), "by": by},
                )
            )

    async def exit_all(self, by: str = "user") -> dict[str, int]:
        """Panic button: turn the kill switch on, cancel waiting trades, exit every
        open trade and flatten any other paper position at market."""
        await self.runtime.update(TradingRuntime, kill_switch=True)
        self._queue(
            Event(
                type=EventType.KILL_SWITCH_CHANGED,
                aggregate_type="trading",
                payload={"kill_switch": True, "by": by},
            )
        )
        cancelled = exited = flattened = 0
        async with self.lock, self.sf() as s:
            plans = list(
                await s.scalars(
                    select(TradePlan).where(
                        TradePlan.status.in_([TradePlanStatus.PENDING, TradePlanStatus.OPEN])
                    )
                )
            )
            held: dict[tuple[uuid.UUID, uuid.UUID, ProductType], int] = {}
            for plan in plans:
                acct = await s.get(BrokerAccount, plan.broker_account_id)
                if acct is None or acct.mode is not ExecutionMode.PAPER:
                    continue
                was_open = plan.status is TradePlanStatus.OPEN
                orders = await self._plan_orders(s, plan.id)
                exiting = any(o.role is OrderRole.EXIT and o.status in WORKING for o in orders)
                if was_open:
                    key = (plan.broker_account_id, plan.instrument_id, plan.product)
                    held[key] = held.get(key, 0) + plan.open_quantity * _direction(plan.side)
                if exiting:
                    continue
                await self._exit_plan(s, plan, None, ExitReason.EXIT_ALL)
                if was_open:
                    exited += 1
                else:
                    cancelled += 1
            for o in await s.scalars(
                select(Order).where(
                    Order.mode == ExecutionMode.PAPER,
                    Order.status.in_(WORKING),
                    Order.trade_plan_id.is_(None),
                )
            ):
                self._set_status(o, OrderStatus.CANCELLED, "exit all")
            for pos in await s.scalars(select(Position).where(Position.quantity != 0)):
                acct = await s.get(BrokerAccount, pos.broker_account_id)
                if acct is None or acct.mode is not ExecutionMode.PAPER:
                    continue
                rest = pos.quantity - held.get(
                    (pos.broker_account_id, pos.instrument_id, pos.product), 0
                )
                if rest == 0:
                    continue
                inst = _req(await s.get(Instrument, pos.instrument_id), "Instrument")
                o = await self._new_order(
                    s,
                    acct,
                    inst,
                    None,
                    Side.SELL if rest > 0 else Side.BUY,
                    abs(rest),
                    OrderType.MARKET,
                    None,
                    None,
                    OrderRole.EXIT,
                )
                o.product = pos.product
                flattened += 1
            await s.commit()
        result = {"cancelled": cancelled, "exited": exited, "flattened": flattened}
        self._queue(
            Event(
                type=EventType.EXIT_ALL,
                aggregate_type="trading",
                payload={**result, "by": by},
            )
        )
        await self._flush_events()
        await self.tick()
        return result

    async def set_kill_switch(self, on: bool, by: str = "user") -> None:
        await self.runtime.update(TradingRuntime, kill_switch=on)
        await self._publish(
            Event(
                type=EventType.KILL_SWITCH_CHANGED,
                aggregate_type="trading",
                payload={"kill_switch": on, "by": by},
            )
        )

    # ------------------------------------------------------------------ tick
    async def tick(self) -> int:
        """Match working paper orders against current prices. Returns fills made."""
        fills = 0
        async with self.lock, self.sf() as s:
            orders = list(
                await s.scalars(
                    select(Order)
                    .where(Order.mode == ExecutionMode.PAPER, Order.status.in_(WORKING))
                    .order_by(Order.created_at)
                )
            )
            if not orders:
                return 0
            now = datetime.now(UTC)
            inst_ids = {o.instrument_id for o in orders}
            instruments = {
                i.id: i
                for i in await s.scalars(select(Instrument).where(Instrument.id.in_(inst_ids)))
            }
            prices = await self.market.ltp(list(instruments.values()))
            accounts: dict[uuid.UUID, AccountRiskSettings] = {}
            for o in orders:
                if o.status not in WORKING:  # cancelled earlier in this tick (OCO)
                    continue
                if o.expires_at and o.expires_at <= now:
                    self._set_status(o, OrderStatus.CANCELLED, "expired")
                    if o.trade_plan_id and o.role is OrderRole.ENTRY:
                        plan = await s.get(TradePlan, o.trade_plan_id)
                        if plan and plan.status is TradePlanStatus.PENDING:
                            self._close_plan(plan, ExitReason.EXPIRED, TradePlanStatus.CANCELLED)
                    continue
                ltp = prices.get(o.instrument_id)
                if ltp is None:
                    continue
                if o.broker_account_id not in accounts:
                    acct = await s.get(BrokerAccount, o.broker_account_id)
                    accounts[o.broker_account_id] = AccountRiskSettings.model_validate(
                        acct.settings if acct else {}
                    )
                settings = accounts[o.broker_account_id]
                inst = instruments[o.instrument_id]
                px = fill_price(o, ltp, settings.slippage_bps, inst.tick_size)
                if px is None:
                    continue
                if await self._fill(s, o, inst, px, settings):
                    fills += 1
            await self._trail(s, instruments, prices)
            await s.commit()
        await self._flush_events()
        return fills

    async def _trail(
        self,
        s: AsyncSession,
        instruments: dict[uuid.UUID, Instrument],
        prices: dict[uuid.UUID, Decimal],
    ) -> None:
        """Track each open trade's best price and apply points/percent trailing."""
        plans = await s.scalars(
            select(TradePlan).where(
                TradePlan.status == TradePlanStatus.OPEN,
                TradePlan.instrument_id.in_(list(prices)),
            )
        )
        for plan in plans:
            ltp = prices[plan.instrument_id]
            best = plan.best_price or plan.entry_price or ltp
            best = max(best, ltp) if plan.side is Side.BUY else min(best, ltp)
            if best != plan.best_price:
                plan.best_price = best
            tr = plan.trailing or {}
            try:
                mode = TrailMode(tr.get("mode", "none"))
                value = Decimal(str(tr.get("value") or "0"))
            except (ValueError, ArithmeticError):
                continue
            inst = instruments.get(plan.instrument_id)
            new = trail_stop(
                plan.side,
                mode,
                value,
                plan.stop_loss,
                best,
                inst.tick_size if inst else Decimal("0.05"),
            )
            if new is not None:
                await self._move_stop(s, plan, new, f"trail:{mode.value}")

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("trading.tick_failed")
            await asyncio.sleep(self.TICK_SECONDS)

    # -------------------------------------------------------------- internals
    async def _fill(
        self,
        s: AsyncSession,
        o: Order,
        inst: Instrument,
        px: Decimal,
        settings: AccountRiskSettings,
    ) -> bool:
        now = datetime.now(UTC)
        qty = o.quantity - o.filled_quantity
        plan = await s.get(TradePlan, o.trade_plan_id) if o.trade_plan_id else None
        if plan is not None and o.role in EXIT_ROLES:
            # Never exit more than the trade still holds (e.g. two exits in one tick).
            if plan.status is not TradePlanStatus.OPEN or plan.open_quantity <= 0:
                self._set_status(o, OrderStatus.CANCELLED, "trade already closed")
                return False
            if qty > plan.open_quantity:
                qty = plan.open_quantity
                o.quantity = o.filled_quantity + qty
        s.add(
            Trade(
                order_id=o.id,
                broker_trade_id=f"paper-{uuid.uuid4().hex[:12]}",
                quantity=qty,
                price=px,
                executed_at=now,
            )
        )
        o.filled_quantity = o.quantity
        o.average_price = px
        self._set_status(o, OrderStatus.FILLED, None)
        self._queue(
            Event(
                type=EventType.TRADE_EXECUTED,
                aggregate_type="order",
                aggregate_id=o.id,
                payload={
                    "symbol": inst.tradingsymbol,
                    "side": o.side,
                    "quantity": qty,
                    "price": str(px),
                    "role": o.role,
                    "trade_plan_id": str(plan.id) if plan else None,
                },
            )
        )

        pos = await s.scalar(
            select(Position).where(
                Position.broker_account_id == o.broker_account_id,
                Position.instrument_id == o.instrument_id,
                Position.product == o.product,
            )
        )
        if pos is None:
            pos = Position(
                broker_account_id=o.broker_account_id,
                instrument_id=o.instrument_id,
                product=o.product,
                quantity=0,
                average_price=Decimal("0"),
                realized_pnl=Decimal("0"),
            )
            s.add(pos)
        pos.quantity, pos.average_price, pos.realized_pnl = apply_fill(
            pos.quantity, pos.average_price, pos.realized_pnl, o.side, qty, px
        )

        if plan is None:
            return True
        plan.charges = (plan.charges or Decimal("0")) + settings.charges_per_order
        acct = _req(await s.get(BrokerAccount, plan.broker_account_id), "Account")
        if o.role is OrderRole.ENTRY and plan.status is TradePlanStatus.PENDING:
            plan.status = TradePlanStatus.OPEN
            plan.entry_price = px
            plan.opened_at = now
            plan.open_quantity = plan.quantity
            plan.best_price = px
            await self._place_exits(s, acct, inst, plan)
            self._queue(
                Event(
                    type=EventType.TRADE_PLAN_OPENED,
                    aggregate_type="trade_plan",
                    aggregate_id=plan.id,
                    payload={
                        "symbol": inst.tradingsymbol,
                        "entry_price": str(px),
                        "quantity": plan.quantity,
                    },
                )
            )
        elif o.role in EXIT_ROLES and plan.status is TradePlanStatus.OPEN:
            if o.role is OrderRole.TARGET:
                reason = ExitReason.TARGET
                legs = legs_of(plan)
                if o.leg is not None and o.leg < len(legs):
                    legs[o.leg].status = "hit"
                    _set_legs(plan, legs)
            elif o.role is OrderRole.STOP:
                init = plan.initial_stop_loss or plan.stop_loss
                moved = (plan.stop_loss - init) * _direction(plan.side) > 0
                reason = ExitReason.TRAILING_STOP if moved else ExitReason.STOP
            else:
                try:
                    reason = ExitReason(o.status_message or "manual")
                except ValueError:
                    reason = ExitReason.MANUAL
            await self._reduce(s, plan, inst, o, qty, px, reason)
        return True

    async def _place_exits(
        self, s: AsyncSession, acct: BrokerAccount, inst: Instrument, plan: TradePlan
    ) -> None:
        exit_side = _opposite(plan.side)
        await self._new_order(
            s,
            acct,
            inst,
            plan,
            exit_side,
            plan.open_quantity,
            OrderType.SL_M,
            None,
            plan.stop_loss,
            OrderRole.STOP,
        )
        for i, leg in enumerate(legs_of(plan)):
            if leg.status != "open":
                continue
            o = await self._new_order(
                s,
                acct,
                inst,
                plan,
                exit_side,
                leg.quantity,
                OrderType.LIMIT,
                leg.price,
                None,
                OrderRole.TARGET,
            )
            o.leg = i

    async def _reduce(
        self,
        s: AsyncSession,
        plan: TradePlan,
        inst: Instrument,
        filled: Order,
        qty: int,
        px: Decimal,
        reason: ExitReason,
    ) -> None:
        """Book an exit of ``qty`` at ``px``; close the plan when nothing is left."""
        entry = plan.entry_price or px
        exited_before = plan.quantity - plan.open_quantity
        plan.gross_pnl = (plan.gross_pnl or Decimal("0")) + (px - entry) * qty * _direction(
            plan.side
        )
        plan.exit_price = ((plan.exit_price or Decimal("0")) * exited_before + px * qty) / (
            exited_before + qty
        )
        plan.open_quantity -= qty
        plan.realized_pnl = plan.gross_pnl - (plan.charges or Decimal("0"))
        orders = await self._plan_orders(s, plan.id)
        if plan.open_quantity <= 0:
            for sib in orders:
                if sib.id != filled.id and sib.status in WORKING:
                    self._set_status(sib, OrderStatus.CANCELLED, "trade closed")
            legs = legs_of(plan)
            for leg in legs:
                if leg.status == "open":
                    leg.status = "cancelled"
            plan.targets = [leg.model_dump(mode="json") for leg in legs]
            self._close_plan(plan, reason, TradePlanStatus.CLOSED)
            return
        # Still holding some: shrink the stop, trim targets that no longer fit.
        for sib in orders:
            if sib.role is OrderRole.STOP and sib.status in WORKING:
                self._modify(sib, quantity=plan.open_quantity)
        legs = legs_of(plan)
        excess = sum(leg.quantity for leg in legs if leg.status == "open") - plan.open_quantity
        for i in reversed(range(len(legs))):
            if excess <= 0:
                break
            leg = legs[i]
            if leg.status != "open":
                continue
            cut = min(leg.quantity, excess)
            excess -= cut
            target_order = next(
                (
                    o
                    for o in orders
                    if o.role is OrderRole.TARGET and o.leg == i and o.status in WORKING
                ),
                None,
            )
            if cut == leg.quantity:
                leg.status = "cancelled"
                if target_order is not None:
                    self._set_status(target_order, OrderStatus.CANCELLED, "quantity already exited")
            else:
                leg.quantity -= cut
                if target_order is not None:
                    self._modify(target_order, quantity=leg.quantity)
        _set_legs(plan, legs)
        self._queue(
            Event(
                type=EventType.TRADE_PLAN_REDUCED,
                aggregate_type="trade_plan",
                aggregate_id=plan.id,
                payload={
                    "symbol": inst.tradingsymbol,
                    "reason": reason,
                    "quantity": qty,
                    "price": str(px),
                    "open_quantity": plan.open_quantity,
                },
            )
        )
        mode = (plan.trailing or {}).get("mode")
        if reason is ExitReason.TARGET and mode == TrailMode.STEP.value:
            new = step_stop(plan.side, entry, legs, plan.stop_loss)
            if new is not None:
                await self._move_stop(s, plan, new, "trail:step")

    def _close_plan(self, plan: TradePlan, reason: ExitReason, status: TradePlanStatus) -> None:
        plan.status = status
        plan.exit_reason = reason
        plan.closed_at = datetime.now(UTC)
        self._queue(
            Event(
                type=EventType.TRADE_PLAN_CLOSED,
                aggregate_type="trade_plan",
                aggregate_id=plan.id,
                payload={
                    "reason": reason,
                    "status": status,
                    "pnl": str(plan.realized_pnl) if plan.realized_pnl is not None else None,
                },
            )
        )

    async def _new_order(
        self,
        s: AsyncSession,
        acct: BrokerAccount,
        inst: Instrument,
        plan: TradePlan | None,
        side: Side,
        qty: int,
        order_type: OrderType,
        price: Decimal | None,
        trigger: Decimal | None,
        role: OrderRole,
        signal_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
        cause: Event | None = None,
    ) -> Order:
        order = Order(
            broker_account_id=acct.id,
            instrument_id=inst.id,
            signal_id=signal_id or (plan.signal_id if plan else None),
            client_order_id=f"mos-{uuid.uuid4().hex[:20]}",
            broker_order_id=f"paper-{uuid.uuid4().hex[:12]}",
            mode=acct.mode,
            side=side,
            order_type=order_type,
            product=plan.product if plan else _product_for(inst),
            quantity=qty,
            price=price,
            trigger_price=trigger,
            status=OrderStatus.OPEN,
            submitted_at=datetime.now(UTC),
            trade_plan_id=plan.id if plan else None,
            role=role,
            expires_at=expires_at,
        )
        s.add(order)
        await s.flush()
        self._queue(
            _event(
                cause,
                EventType.ORDER_CREATED,
                "order",
                order.id,
                {
                    "symbol": inst.tradingsymbol,
                    "side": side,
                    "quantity": qty,
                    "type": order_type,
                    "role": role,
                    "price": str(price) if price is not None else None,
                    "trigger": str(trigger) if trigger is not None else None,
                    "mode": acct.mode,
                },
            )
        )
        return order

    def _set_status(self, o: Order, status: OrderStatus, message: str | None) -> None:
        old = o.status
        o.status = status
        if message:
            o.status_message = message
        self._queue(
            Event(
                type=EventType.ORDER_STATUS_CHANGED,
                aggregate_type="order",
                aggregate_id=o.id,
                payload={"from": old, "to": status, "message": message},
            )
        )

    def _modify(
        self, o: Order, *, quantity: int | None = None, trigger: Decimal | None = None
    ) -> None:
        changes: dict[str, object] = {}
        if quantity is not None and quantity != o.quantity:
            o.quantity = quantity
            changes["quantity"] = quantity
        if trigger is not None and trigger != o.trigger_price:
            o.trigger_price = trigger
            changes["trigger"] = str(trigger)
        if changes:
            self._queue(
                Event(
                    type=EventType.ORDER_MODIFIED,
                    aggregate_type="order",
                    aggregate_id=o.id,
                    payload=changes,
                )
            )

    async def _plan_orders(self, s: AsyncSession, plan_id: uuid.UUID) -> Sequence[Order]:
        return list(await s.scalars(select(Order).where(Order.trade_plan_id == plan_id)))

    async def realized_today(self, s: AsyncSession, account_id: uuid.UUID) -> Decimal:
        start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        total = await s.scalar(
            select(func.coalesce(func.sum(TradePlan.realized_pnl), 0)).where(
                TradePlan.broker_account_id == account_id,
                TradePlan.closed_at >= start.astimezone(UTC),
            )
        )
        return Decimal(str(total or 0))

    def _queue(self, e: Event) -> None:
        self._pending_events.append(e)

    async def _flush_events(self) -> None:
        events, self._pending_events = self._pending_events, []
        for e in events:
            await self.bus.publish(e)

    async def _publish(self, e: Event) -> None:
        await self.bus.publish(e)


def _event(
    cause: Event | None, type_: str, agg: str, agg_id: uuid.UUID, payload: dict[str, object]
) -> Event:
    if cause is not None:
        return cause.caused(type_, aggregate_type=agg, aggregate_id=agg_id, payload=payload)
    return Event(type=type_, aggregate_type=agg, aggregate_id=agg_id, payload=payload)
