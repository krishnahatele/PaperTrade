from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import RawMessageStatus


class RawMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An unprocessed inbound message (e.g. a Telegram post), stored verbatim."""

    __tablename__ = "raw_messages"
    __table_args__ = (UniqueConstraint("source_id", "external_message_id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signal_sources.id", ondelete="CASCADE"), index=True
    )
    external_message_id: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    received_at: Mapped[datetime]
    status: Mapped[RawMessageStatus] = mapped_column(
        str_enum(RawMessageStatus, "raw_message_status"),
        default=RawMessageStatus.PENDING,
        index=True,
    )
