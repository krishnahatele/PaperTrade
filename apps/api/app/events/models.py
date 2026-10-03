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
    INSTRUMENTS_SYNCED = "instruments.synced"
    SIGNAL_SOURCE_CREATED = "signal_source.created"
    SIGNAL_SOURCE_UPDATED = "signal_source.updated"
    SIGNAL_SOURCE_DELETED = "signal_source.deleted"
    BROKER_ACCOUNT_CREATED = "broker_account.created"
    RAW_MESSAGE_RECEIVED = "raw_message.received"
    RAW_MESSAGE_PROCESSED = "raw_message.processed"
    SIGNAL_CREATED = "signal.created"
    SIGNAL_STATUS_CHANGED = "signal.status_changed"
    ORDER_CREATED = "order.created"
    ORDER_STATUS_CHANGED = "order.status_changed"
    TRADE_EXECUTED = "trade.executed"
    TRADE_PLAN_CREATED = "trade_plan.created"
    TRADE_PLAN_OPENED = "trade_plan.opened"
    TRADE_PLAN_CLOSED = "trade_plan.closed"
    TRADE_PLAN_UPDATED = "trade_plan.updated"  # SL / targets / trailing changed
    TRADE_PLAN_REDUCED = "trade_plan.reduced"  # partial exit (TP1 hit, exit some qty)
    ORDER_MODIFIED = "order.modified"
    EXIT_ALL = "trading.exit_all"
    KILL_SWITCH_CHANGED = "trading.kill_switch_changed"
    NEWS_RECEIVED = "news.received"
    NEWS_ALERT = "news.alert"  # a headline matched a watch keyword
    MARKET_ALERT = "market.alert"  # a watched instrument moved sharply
    REPLAY_FINISHED = "replay.finished"
    BOT_LINKED = "bot.linked"
    SIGNAL_EXECUTION_SKIPPED = "signal.execution_skipped"
    MANUAL_PRICE_SET = "market.manual_price_set"
    BROKER_ACCOUNT_UPDATED = "broker_account.updated"
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
