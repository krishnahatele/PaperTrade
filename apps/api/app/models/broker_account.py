from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import BrokerName, ExecutionMode


class BrokerAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A brokerage account (or the internal paper account) orders are routed to.

    Credentials are never stored here. ``credentials_ref`` points at a secret in
    an external store (env var name / vault path).
    """

    __tablename__ = "broker_accounts"

    broker: Mapped[BrokerName] = mapped_column(str_enum(BrokerName, "broker_name"))
    label: Mapped[str] = mapped_column(String(128), unique=True)
    mode: Mapped[ExecutionMode] = mapped_column(
        str_enum(ExecutionMode, "execution_mode"), default=ExecutionMode.PAPER
    )
    external_account_id: Mapped[str | None] = mapped_column(String(64))
    credentials_ref: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
