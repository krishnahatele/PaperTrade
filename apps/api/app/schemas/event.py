from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class EventRead(ORMModel):
    id: uuid.UUID
    event_type: str
    aggregate_type: str | None
    aggregate_id: uuid.UUID | None
    payload: dict[str, Any]
    correlation_id: uuid.UUID | None
    causation_id: uuid.UUID | None
    occurred_at: datetime
    recorded_at: datetime
