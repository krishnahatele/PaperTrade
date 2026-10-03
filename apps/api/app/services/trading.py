"""Order management and the paper-trading engine.

* ``execute_signal`` turns a validated signal into a *trade plan*: risk checks,
  position sizing, and an entry order.
* ``tick`` (every ~2 s in the background) matches working paper orders against
  last-traded prices, books fills into positions, and manages each plan's
  bracket: once the entry fills, a stop-loss (SL-M) and a target (LIMIT) are
  placed; when one fills the other is cancelled.

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
)
from app.services.market_data import MarketDataService
from app.services.risk import AccountRiskSettings, apply_fill, round_to_tick, size_position
from app.services.runtime import RuntimeStore, TradingRuntime

log = get_logger("marketos.trading")
IST = ZoneInfo("Asia/Kolkata")
WORKING = (OrderStatus.OPEN, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
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
            target = targets[min(settings.target_index, len(targets)) - 1] if targets else None
            plan = TradePlan(
                signal_id=sig.id,
                broker_account_id=acct.id,
                instrument_id=inst.id,
                side=sig.side,
                product=_product_for(inst),
                quantity=sizing.quantity,
                planned_entry=ref,
                stop_loss=sig.stop_loss,
                target=target,
                status=TradePlanStatus.PENDING,
            )
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
                        "target": str(target) if target else None,
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
                    self._close_plan(plan, None, ExitReason.CANCELLED, TradePlanStatus.CANCELLED)
            await s.commit()
            await s.refresh(order)
        await self._flush_events()
        return order

    async def close_plan(self, plan_id: uuid.UUID) -> TradePlan:
        async with self.lock, self.sf() as s:
            plan = await s.get(TradePlan, plan_id)
            if plan is None:
                raise NotFoundError("Trade not found")
            orders = await self._plan_orders(s, plan.id)
            if plan.status is TradePlanStatus.PENDING:
                for o in orders:
                    if o.status in WORKING:
                        self._set_status(o, OrderStatus.CANCELLED, "trade cancelled")
                self._close_plan(plan, None, ExitReason.CANCELLED, TradePlanStatus.CANCELLED)
            elif plan.status is TradePlanStatus.OPEN:
                if any(o.role is OrderRole.EXIT and o.status in WORKING for o in orders):
                    raise InvalidInputError("An exit order is already working.")
                for o in orders:
                    if o.role in (OrderRole.STOP, OrderRole.TARGET) and o.status in WORKING:
                        self._set_status(o, OrderStatus.CANCELLED, "manual exit")
                acct = _req(await s.get(BrokerAccount, plan.broker_account_id), "Account")
                inst = _req(await s.get(Instrument, plan.instrument_id), "Instrument")
                await self._new_order(
                    s,
                    acct,
                    inst,
                    plan,
                    _opposite(plan.side),
                    plan.quantity,
                    OrderType.MARKET,
                    None,
                    None,
                    OrderRole.EXIT,
                )
            else:
                raise InvalidInputError(f"Trade is already {plan.status}.")
            await s.commit()
        await self._flush_events()
        await self.tick()
        async with self.sf() as s:
            return _req(await s.get(TradePlan, plan_id), "Trade")

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
                            self._close_plan(
                                plan, None, ExitReason.EXPIRED, TradePlanStatus.CANCELLED
                            )
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
                await self._fill(s, o, inst, px, settings)
                fills += 1
            await s.commit()
        await self._flush_events()
        return fills

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
    ) -> None:
        now = datetime.now(UTC)
        qty = o.quantity - o.filled_quantity
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

        if o.trade_plan_id is None:
            return
        plan = await s.get(TradePlan, o.trade_plan_id)
        if plan is None:
            return
        plan.charges = (plan.charges or Decimal("0")) + settings.charges_per_order
        acct = _req(await s.get(BrokerAccount, plan.broker_account_id), "Account")
        if o.role is OrderRole.ENTRY and plan.status is TradePlanStatus.PENDING:
            plan.status = TradePlanStatus.OPEN
            plan.entry_price = px
            plan.opened_at = now
            exit_side = _opposite(plan.side)
            await self._new_order(
                s,
                acct,
                inst,
                plan,
                exit_side,
                plan.quantity,
                OrderType.SL_M,
                None,
                plan.stop_loss,
                OrderRole.STOP,
            )
            if plan.target is not None:
                await self._new_order(
                    s,
                    acct,
                    inst,
                    plan,
                    exit_side,
                    plan.quantity,
                    OrderType.LIMIT,
                    plan.target,
                    None,
                    OrderRole.TARGET,
                )
            self._queue(
                Event(
                    type=EventType.TRADE_PLAN_OPENED,
                    aggregate_type="trade_plan",
                    aggregate_id=plan.id,
                    payload={"symbol": inst.tradingsymbol, "entry_price": str(px)},
                )
            )
        elif (
            o.role in (OrderRole.STOP, OrderRole.TARGET, OrderRole.EXIT)
            and plan.status is TradePlanStatus.OPEN
        ):
            for sib in await self._plan_orders(s, plan.id):
                if sib.id != o.id and sib.status in WORKING:
                    self._set_status(sib, OrderStatus.CANCELLED, "other exit filled (OCO)")
            reason = {OrderRole.STOP: ExitReason.STOP, OrderRole.TARGET: ExitReason.TARGET}.get(
                o.role, ExitReason.MANUAL
            )
            self._close_plan(plan, px, reason, TradePlanStatus.CLOSED)

    def _close_plan(
        self, plan: TradePlan, exit_px: Decimal | None, reason: ExitReason, status: TradePlanStatus
    ) -> None:
        plan.status = status
        plan.exit_reason = reason
        plan.closed_at = datetime.now(UTC)
        if exit_px is not None and plan.entry_price is not None:
            direction = 1 if plan.side is Side.BUY else -1
            plan.exit_price = exit_px
            plan.realized_pnl = (exit_px - plan.entry_price) * plan.quantity * direction - (
                plan.charges or Decimal("0")
            )
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
