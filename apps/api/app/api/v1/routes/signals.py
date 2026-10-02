from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import BusDep, PageDep, SessionDep
from app.models import Signal
from app.models.enums import SignalStatus
from app.schemas.common import Page
from app.schemas.signal import SignalCreate, SignalRead
from app.services.catalog import SignalService
from app.services.repository import Repository

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=Page[SignalRead])
async def list_signals(
    session: SessionDep,
    page: PageDep,
    status_: SignalStatus | None = Query(default=None, alias="status"),
    source_id: uuid.UUID | None = None,
) -> Page[SignalRead]:
    filters = []
    if status_ is not None:
        filters.append(Signal.status == status_)
    if source_id is not None:
        filters.append(Signal.source_id == source_id)
    rows, total = await Repository(session, Signal).list(
        filters=filters,
        order_by=[Signal.created_at.desc()],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[SignalRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{signal_id}", response_model=SignalRead)
async def get_signal(signal_id: uuid.UUID, session: SessionDep) -> Signal:
    return await Repository(session, Signal).get(signal_id)


@router.post(
    "",
    response_model=SignalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a signal manually (no parsing, no execution)",
)
async def create_signal(data: SignalCreate, session: SessionDep, bus: BusDep) -> Signal:
    return await SignalService(session, bus).create_manual(data)
