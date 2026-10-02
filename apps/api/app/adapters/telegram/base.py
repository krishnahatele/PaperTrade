"""TelegramAdapter: reads messages from configured channels.

Planned implementation: an MTProto user client (e.g. Telethon). Ingestion is
out of scope for Phase 0; only the contract is defined.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.adapters.base import AdapterHealth


class InboundMessage(BaseModel):
    channel_id: str
    message_id: str
    text: str
    sent_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


MessageHandler = Callable[[InboundMessage], Awaitable[None]]


class TelegramAdapter(ABC):
    name: str

    @abstractmethod
    async def health(self) -> AdapterHealth: ...

    @abstractmethod
    async def start(self, channel_ids: Sequence[str], on_message: MessageHandler) -> None:
        """Begin listening; ``on_message`` is awaited for every new message."""

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def fetch_history(self, channel_id: str, limit: int = 100) -> list[InboundMessage]: ...
