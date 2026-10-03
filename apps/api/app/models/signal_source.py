from __future__ import annotations

from typing import Any

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import SignalSourceKind


class SignalSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Where signals come from: a Telegram channel, manual entry, a webhook."""

    __tablename__ = "signal_sources"
    __table_args__ = (UniqueConstraint("kind", "external_id"),)

    kind: Mapped[SignalSourceKind] = mapped_column(str_enum(SignalSourceKind, "signal_source_kind"))
    name: Mapped[str] = mapped_column(String(128))
    # e.g. Telegram channel id / username. Null for manual sources.
    external_id: Mapped[str | None] = mapped_column(String(128))
    is_enabled: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
