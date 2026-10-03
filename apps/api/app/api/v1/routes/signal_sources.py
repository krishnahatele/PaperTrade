from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import BusDep, ContainerDep, PageDep, SessionDep
from app.models import RawMessage, SignalSource
from app.schemas.common import Page
from app.schemas.raw_message import RawMessageRead
from app.schemas.signal_source import SignalSourceCreate, SignalSourceRead, SignalSourceUpdate
from app.services.catalog import SignalSourceService
from app.services.repository import Repository

router = APIRouter(prefix="/signal-sources", tags=["signal-sources"])


@router.get("", response_model=Page[SignalSourceRead])
async def list_signal_sources(session: SessionDep, page: PageDep) -> Page[SignalSourceRead]:
    rows, total = await Repository(session, SignalSource).list(
        order_by=[SignalSource.name], limit=page.limit, offset=page.offset
    )
    return Page(
        items=[SignalSourceRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{source_id}", response_model=SignalSourceRead)
async def get_signal_source(source_id: uuid.UUID, session: SessionDep) -> SignalSource:
    return await Repository(session, SignalSource).get(source_id)


@router.post("", response_model=SignalSourceRead, status_code=status.HTTP_201_CREATED)
async def create_signal_source(
    data: SignalSourceCreate, session: SessionDep, bus: BusDep, container: ContainerDep
) -> SignalSource:
    src = await SignalSourceService(session, bus).create(data)
    await container.telegram.start_listening()
    return src


@router.patch("/{source_id}", response_model=SignalSourceRead)
async def update_signal_source(
    source_id: uuid.UUID,
    data: SignalSourceUpdate,
    session: SessionDep,
    bus: BusDep,
    container: ContainerDep,
) -> SignalSource:
    src = await SignalSourceService(session, bus).update(source_id, data)
    await container.telegram.start_listening()
    return src


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signal_source(
    source_id: uuid.UUID, session: SessionDep, bus: BusDep, container: ContainerDep
) -> None:
    await SignalSourceService(session, bus).delete(source_id)
    await container.telegram.start_listening()


@router.get("/{source_id}/messages", response_model=Page[RawMessageRead])
async def list_source_messages(
    source_id: uuid.UUID, session: SessionDep, page: PageDep
) -> Page[RawMessageRead]:
    await Repository(session, SignalSource).get(source_id)
    rows, total = await Repository(session, RawMessage).list(
        filters=[RawMessage.source_id == source_id],
        order_by=[RawMessage.received_at.desc()],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[RawMessageRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
