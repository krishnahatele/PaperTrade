"""Orders, trade plans, positions and portfolio (paper trading).

Live accounts are refused by the engine; see docs/architecture.md (safety model).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import ContainerDep, PageDep, SessionDep
from app.container import Container
from app.core.errors import InvalidInputError
from app.models import BrokerAccount, Instrument, Order, Position, Trade, TradePlan
from app.models.enums import OrderStatus, TradePlanStatus
from app.schemas.common import Page
from app.schemas.order import OrderRead, PositionRead, TradeRead
from app.schemas.trading import (
    AccountSummary,
    ExecuteBody,
    ManualOrderBody,
    PositionView,
    TradePlanRead,
)
from app.services.repository import Repository
from app.services.risk import AccountRiskSettings
from app.services.trading import SkipError

router = APIRouter(tags=["trading"])


async def _account_id(container: Container, given: uuid.UUID | None) -> uuid.UUID:
    if given is not None:
        return given
    return (await container.engine.ensure_paper_account()).id


# ---------------------------------------------------------------- orders
@router.get("/orders", response_model=Page[OrderRead])
async def list_orders(
    session: SessionDep,
    page: PageDep,
    status_: OrderStatus | None = Query(default=None, alias="status"),
    broker_account_id: uuid.UUID | None = None,
    trade_plan_id: uuid.UUID | None = None,
) -> Page[OrderRead]:
    filters = []
    if status_ is not None:
        filters.append(Order.status == status_)
    if broker_account_id is not None:
        filters.append(Order.broker_account_id == broker_account_id)
    if trade_plan_id is not None:
        filters.append(Order.trade_plan_id == trade_plan_id)
    rows, total = await Repository(session, Order).list(
        filters=filters, order_by=[Order.created_at.desc()], limit=page.limit, offset=page.offset
    )
    return Page(
        items=[OrderRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/orders",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place a manual paper order",
)
async def place_order(body: ManualOrderBody, container: ContainerDep) -> Order:
    acct = await _account_id(container, body.broker_account_id)
    return await container.engine.place_manual_order(
        acct,
        body.instrument_id,
        body.side,
        body.quantity,
        body.order_type,
        body.price,
        body.trigger_price,
    )


@router.get("/orders/{order_id}", response_model=OrderRead)
async def get_order(order_id: uuid.UUID, session: SessionDep) -> Order:
    return await Repository(session, Order).get(order_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(order_id: uuid.UUID, container: ContainerDep) -> Order:
    return await container.engine.cancel_order(order_id)


@router.get("/orders/{order_id}/trades", response_model=list[TradeRead])
async def list_order_trades(order_id: uuid.UUID, session: SessionDep) -> list[Trade]:
    await Repository(session, Order).get(order_id)
    rows, _ = await Repository(session, Trade).list(
        filters=[Trade.order_id == order_id], order_by=[Trade.executed_at], limit=500
    )
    return rows


# ----------------------------------------------------------- trade plans
async def _enrich(
    container: Container, session: SessionDep, plans: list[TradePlan]
) -> list[TradePlanRead]:
    inst_ids = {p.instrument_id for p in plans}
    insts = (
        {
            i.id: i
            for i in await session.scalars(select(Instrument).where(Instrument.id.in_(inst_ids)))
        }
        if inst_ids
        else {}
    )
    open_insts = [insts[p.instrument_id] for p in plans if p.status is TradePlanStatus.OPEN]
    prices = await container.market.ltp(open_insts) if open_insts else {}
    out = []
    for p in plans:
        r = TradePlanRead.model_validate(p)
        inst = insts.get(p.instrument_id)
        r.tradingsymbol = inst.tradingsymbol if inst else None
        ltp = prices.get(p.instrument_id)
        r.ltp = ltp
        if ltp is not None and p.entry_price is not None and p.status is TradePlanStatus.OPEN:
            d = 1 if p.side.value == "BUY" else -1
            r.unrealized_pnl = (ltp - p.entry_price) * p.quantity * d
        out.append(r)
    return out


@router.get(
    "/trades", response_model=Page[TradePlanRead], summary="Managed trades (entry + SL + target)"
)
async def list_trades(
    session: SessionDep,
    container: ContainerDep,
    page: PageDep,
    status_: TradePlanStatus | None = Query(default=None, alias="status"),
    broker_account_id: uuid.UUID | None = None,
) -> Page[TradePlanRead]:
    filters = []
    if status_ is not None:
        filters.append(TradePlan.status == status_)
    if broker_account_id is not None:
        filters.append(TradePlan.broker_account_id == broker_account_id)
    rows, total = await Repository(session, TradePlan).list(
        filters=filters,
        order_by=[TradePlan.created_at.desc()],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=await _enrich(container, session, rows),
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/trades/{plan_id}", response_model=TradePlanRead)
async def get_trade(
    plan_id: uuid.UUID, session: SessionDep, container: ContainerDep
) -> TradePlanRead:
    plan = await Repository(session, TradePlan).get(plan_id)
    return (await _enrich(container, session, [plan]))[0]


@router.post(
    "/trades/{plan_id}/close", response_model=TradePlanRead, summary="Exit at market / cancel"
)
async def close_trade(
    plan_id: uuid.UUID, container: ContainerDep, session: SessionDep
) -> TradePlanRead:
    plan = await container.engine.close_plan(plan_id)
    return (await _enrich(container, session, [plan]))[0]


@router.post(
    "/signals/{signal_id}/execute",
    response_model=TradePlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Execute a validated signal now (paper)",
)
async def execute_signal(
    signal_id: uuid.UUID,
    container: ContainerDep,
    session: SessionDep,
    body: ExecuteBody | None = None,
) -> TradePlanRead:
    acct = await _account_id(container, body.broker_account_id if body else None)
    try:
        plan = await container.engine.execute_signal(signal_id, acct)
    except SkipError as exc:
        raise InvalidInputError(f"Not executed: {exc.reason}.") from exc
    return (await _enrich(container, session, [plan]))[0]


# ------------------------------------------------------------- positions
@router.get("/positions", response_model=Page[PositionRead])
async def list_positions(
    session: SessionDep, page: PageDep, broker_account_id: uuid.UUID | None = None
) -> Page[PositionRead]:
    filters = []
    if broker_account_id is not None:
        filters.append(Position.broker_account_id == broker_account_id)
    rows, total = await Repository(session, Position).list(
        filters=filters, order_by=[Position.updated_at.desc()], limit=page.limit, offset=page.offset
    )
    return Page(
        items=[PositionRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/portfolio/positions", response_model=list[PositionView], summary="Positions with live P&L"
)
async def portfolio_positions(
    session: SessionDep, container: ContainerDep, include_closed: bool = False
) -> list[PositionView]:
    q = select(Position, Instrument).join(Instrument, Instrument.id == Position.instrument_id)
    if not include_closed:
        q = q.where(Position.quantity != 0)
    rows = (await session.execute(q.order_by(Position.updated_at.desc()))).all()
    prices = await container.market.ltp([i for _, i in rows]) if rows else {}
    out = []
    for pos, inst in rows:
        ltp = prices.get(inst.id)
        unreal = (
            (ltp - pos.average_price) * pos.quantity if ltp is not None and pos.quantity else None
        )
        out.append(
            PositionView(
                id=pos.id,
                broker_account_id=pos.broker_account_id,
                instrument_id=inst.id,
                tradingsymbol=inst.tradingsymbol,
                product=pos.product,
                quantity=pos.quantity,
                average_price=pos.average_price,
                realized_pnl=pos.realized_pnl,
                ltp=ltp,
                unrealized_pnl=unreal,
            )
        )
    return out


@router.get("/portfolio/summary", response_model=list[AccountSummary])
async def portfolio_summary(session: SessionDep, container: ContainerDep) -> list[AccountSummary]:
    await container.engine.ensure_paper_account()
    accounts = list(await session.scalars(select(BrokerAccount).order_by(BrokerAccount.label)))
    positions = await portfolio_positions(session, container)
    out = []
    for a in accounts:
        settings = AccountRiskSettings.model_validate(a.settings)
        counts = dict(
            (
                await session.execute(
                    select(TradePlan.status, func.count())
                    .where(TradePlan.broker_account_id == a.id)
                    .group_by(TradePlan.status)
                )
            ).all()
        )
        closed = list(
            await session.scalars(
                select(TradePlan.realized_pnl).where(
                    TradePlan.broker_account_id == a.id, TradePlan.status == TradePlanStatus.CLOSED
                )
            )
        )
        wins = sum(1 for x in closed if x is not None and x > 0)
        out.append(
            AccountSummary(
                broker_account_id=a.id,
                label=a.label,
                mode=a.mode.value,
                capital=settings.capital,
                realized_today=await container.engine.realized_today(session, a.id),
                realized_total=sum((x for x in closed if x is not None), Decimal("0")),
                unrealized=sum(
                    (
                        p.unrealized_pnl
                        for p in positions
                        if p.broker_account_id == a.id and p.unrealized_pnl is not None
                    ),
                    Decimal("0"),
                ),
                open_trades=counts.get(TradePlanStatus.OPEN, 0),
                pending_trades=counts.get(TradePlanStatus.PENDING, 0),
                closed_trades=counts.get(TradePlanStatus.CLOSED, 0),
                win_rate=(Decimal(wins) / len(closed) * 100).quantize(Decimal("0.1"))
                if closed
                else None,
            )
        )
    return out
