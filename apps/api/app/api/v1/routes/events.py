from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import PageDep, SessionDep
from app.models import EventRecord
from app.schemas.common import Page
from app.schemas.event import EventRead
from app.services.repository import Repository

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=Page[EventRead], summary="Audit log of domain events")
async def list_events(
    session: SessionDep,
    page: PageDep,
    event_type: str | None = Query(default=None, max_length=128),
    aggregate_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> Page[EventRead]:
    filters = []
    if event_type:
        filters.append(EventRecord.event_type == event_type)
    if aggregate_id is not None:
        filters.append(EventRecord.aggregate_id == aggregate_id)
    if correlation_id is not None:
        filters.append(EventRecord.correlation_id == correlation_id)
    rows, total = await Repository(session, EventRecord).list(
        filters=filters,
        order_by=[EventRecord.occurred_at.desc()],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[EventRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
