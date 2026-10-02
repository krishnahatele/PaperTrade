"""The Event envelope shared by every publisher and subscriber."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    """Known event types. Names are ``<aggregate>.<past-tense-verb>``.

    Later phases add to this list; consumers must tolerate unknown types.
    """

    SYSTEM_STARTED = "system.started"
    SYSTEM_STOPPING = "system.stopping"
    INSTRUMENT_CREATED = "instrument.created"
    SIGNAL_SOURCE_CREATED = "signal_source.created"
    BROKER_ACCOUNT_CREATED = "broker_account.created"
    RAW_MESSAGE_RECEIVED = "raw_message.received"
    SIGNAL_CREATED = "signal.created"
    SIGNAL_STATUS_CHANGED = "signal.status_changed"
    ORDER_CREATED = "order.created"
    ORDER_STATUS_CHANGED = "order.status_changed"
    TRADE_EXECUTED = "trade.executed"
    INTEGRATION_UPDATED = "integration.updated"
    SETTINGS_UPDATED = "settings.updated"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """Immutable domain event.

    ``correlation_id`` ties together every event caused by one external trigger
    (e.g. one Telegram message); ``causation_id`` is the id of the event that
    directly caused this one.
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    occurred_at: datetime = Field(default_factory=_utcnow)
    aggregate_type: str | None = None
    aggregate_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    causation_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def caused(self, type: str, **kwargs: Any) -> Event:
        """Create a follow-up event that inherits correlation from this one."""
        return Event(
            type=type,
            correlation_id=self.correlation_id or self.id,
            causation_id=self.id,
            **kwargs,
        )
