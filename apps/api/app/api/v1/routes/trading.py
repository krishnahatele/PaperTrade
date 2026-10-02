"""Read-only views of orders, trades and positions.

There is deliberately no endpoint that places, modifies or cancels orders in
Phase 0.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import PageDep, SessionDep
from app.models import Order, Position, Trade
from app.models.enums import OrderStatus
from app.schemas.common import Page
from app.schemas.order import OrderRead, PositionRead, TradeRead
from app.services.repository import Repository

router = APIRouter(tags=["trading (read-only)"])


@router.get("/orders", response_model=Page[OrderRead])
async def list_orders(
    session: SessionDep,
    page: PageDep,
    status_: OrderStatus | None = Query(default=None, alias="status"),
    broker_account_id: uuid.UUID | None = None,
) -> Page[OrderRead]:
    filters = []
    if status_ is not None:
        filters.append(Order.status == status_)
    if broker_account_id is not None:
        filters.append(Order.broker_account_id == broker_account_id)
    rows, total = await Repository(session, Order).list(
        filters=filters,
        order_by=[Order.created_at.desc()],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[OrderRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/orders/{order_id}", response_model=OrderRead)
async def get_order(order_id: uuid.UUID, session: SessionDep) -> Order:
    return await Repository(session, Order).get(order_id)


@router.get("/orders/{order_id}/trades", response_model=list[TradeRead])
async def list_order_trades(order_id: uuid.UUID, session: SessionDep) -> list[Trade]:
    await Repository(session, Order).get(order_id)
    rows, _ = await Repository(session, Trade).list(
        filters=[Trade.order_id == order_id], order_by=[Trade.executed_at], limit=500
    )
    return rows


@router.get("/positions", response_model=Page[PositionRead])
async def list_positions(
    session: SessionDep,
    page: PageDep,
    broker_account_id: uuid.UUID | None = None,
) -> Page[PositionRead]:
    filters = []
    if broker_account_id is not None:
        filters.append(Position.broker_account_id == broker_account_id)
    rows, total = await Repository(session, Position).list(
        filters=filters,
        order_by=[Position.updated_at.desc()],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[PositionRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
