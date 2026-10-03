from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import BusDep, ContainerDep, PageDep, SessionDep
from app.core.errors import InvalidInputError
from app.events import Event, EventType
from app.models import Signal
from app.models.enums import SignalStatus
from app.schemas.common import Page
from app.schemas.signal import (
    ParsePreview,
    ParsePreviewBody,
    SignalCreate,
    SignalRead,
    SignalReview,
)
from app.services.catalog import SignalService
from app.services.repository import Repository

router = APIRouter(prefix="/signals", tags=["signals"])

# Manual review may move a signal between these states only.
_REVIEW_TRANSITIONS: dict[SignalStatus, set[SignalStatus]] = {
    SignalStatus.NEW: {SignalStatus.VALIDATED, SignalStatus.REJECTED},
    SignalStatus.VALIDATED: {SignalStatus.NEW, SignalStatus.REJECTED, SignalStatus.CANCELLED},
    SignalStatus.REJECTED: {SignalStatus.NEW},
    SignalStatus.EXPIRED: {SignalStatus.NEW},
}


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


@router.post(
    "/parse-preview",
    response_model=ParsePreview,
    summary="Run the parser on any text without storing anything",
)
async def parse_preview(body: ParsePreviewBody, container: ContainerDep) -> ParsePreview:
    outcome = await container.pipeline.parse_text(
        body.text, allow_llm=body.use_llm, force_llm=body.force_llm
    )
    p = outcome.parsed
    inst = await container.instruments.resolve(p) if p.is_signal else None
    return ParsePreview(
        parser=outcome.parser,
        is_signal=p.is_signal,
        reason=p.reason,
        side=p.side.value if p.side else None,
        symbol_text=p.symbol_text,
        underlying=p.underlying,
        instrument_type=p.instrument_type.value if p.instrument_type else None,
        strike=p.strike,
        expiry_text=p.expiry_text,
        entry_low=p.entry_low,
        entry_high=p.entry_high,
        stop_loss=p.stop_loss,
        targets=p.targets,
        confidence=p.confidence,
        warnings=p.warnings,
        llm_error=outcome.llm_error,
        instrument_id=inst.id if inst else None,
        instrument_tradingsymbol=inst.tradingsymbol if inst else None,
    )


@router.get("/{signal_id}", response_model=SignalRead)
async def get_signal(signal_id: uuid.UUID, session: SessionDep) -> Signal:
    return await Repository(session, Signal).get(signal_id)


@router.post(
    "",
    response_model=SignalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a signal manually",
)
async def create_signal(data: SignalCreate, session: SessionDep, bus: BusDep) -> Signal:
    return await SignalService(session, bus).create_manual(data)


@router.patch("/{signal_id}", response_model=SignalRead, summary="Review / correct a signal")
async def review_signal(
    signal_id: uuid.UUID, body: SignalReview, session: SessionDep, bus: BusDep
) -> Signal:
    sig = await Repository(session, Signal).get(signal_id)
    old_status = sig.status
    changes = body.model_dump(exclude_none=True)
    new_status = changes.pop("status", None)
    if "targets" in changes:
        changes["targets"] = [str(t) for t in changes["targets"]]
    for k, v in changes.items():
        setattr(sig, k, v)
    if new_status is not None and new_status != old_status:
        if new_status not in _REVIEW_TRANSITIONS.get(old_status, set()):
            raise InvalidInputError(f"Cannot change a {old_status} signal to {new_status}.")
        if new_status is SignalStatus.VALIDATED and (
            sig.instrument_id is None or sig.stop_loss is None
        ):
            raise InvalidInputError("A signal needs an instrument and a stop loss to be validated.")
        sig.status = new_status
    await session.commit()
    await session.refresh(sig)
    if sig.status != old_status:
        await bus.publish(
            Event(
                type=EventType.SIGNAL_STATUS_CHANGED,
                aggregate_type="signal",
                aggregate_id=sig.id,
                payload={"from": old_status, "to": sig.status, "by": "review"},
            )
        )
    return sig
