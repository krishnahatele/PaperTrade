from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.models.enums import RawMessageStatus
from app.schemas.common import ReadModel


class RawMessageRead(ReadModel):
    source_id: uuid.UUID
    external_message_id: str
    content: str
    payload: dict[str, Any]
    received_at: datetime
    status: RawMessageStatus
