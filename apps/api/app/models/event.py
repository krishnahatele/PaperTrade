from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventRecord(Base):
    """Append-only log of domain events published on the EventBus.

    Rows are never updated or deleted by the application; this is the audit
    trail for everything that happens in the system.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_events_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str | None] = mapped_column(String(64))
    aggregate_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    causation_id: Mapped[uuid.UUID | None]
    occurred_at: Mapped[datetime]
    recorded_at: Mapped[datetime] = mapped_column(server_default=func.now())
