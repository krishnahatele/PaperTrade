from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.signal import SignalRead

router = APIRouter(prefix="/messages", tags=["signal-sources"])


@router.post(
    "/{message_id}/parse",
    response_model=SignalRead | None,
    summary="Re-run the parser on a stored raw message",
)
async def reparse(message_id: uuid.UUID, container: ContainerDep) -> SignalRead | None:
    sig = await container.pipeline.process(message_id)
    return SignalRead.model_validate(sig) if sig else None
