"""TelegramAdapter: a logged-in Telegram *user* session that reads channels.

The real implementation is Telethon (MTProto). Logging in is a two/three step
flow: request a code to the phone number, submit the code, and (if the account
has two-step verification) submit the cloud password. The resulting session
string is stored encrypted by the caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.adapters.base import AdapterHealth
from app.core.errors import FeatureDisabledError


class InboundMessage(BaseModel):
    channel_id: str
    message_id: str
    text: str
    sent_at: datetime
    reply_to_message_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TelegramChannel(BaseModel):
    id: str
    title: str
    username: str | None = None
    kind: str  # "channel" | "group"


class LoginStep(StrEnum):
    CODE = "code"
    PASSWORD = "password"  # noqa: S105 - step name
    DONE = "done"


MessageHandler = Callable[[InboundMessage], Awaitable[None]]


class TelegramAdapter(ABC):
    name: str

    @abstractmethod
    async def health(self) -> AdapterHealth: ...

    # --- login ------------------------------------------------------------
    @abstractmethod
    async def is_authorized(self) -> bool: ...

    @abstractmethod
    async def send_login_code(self, phone: str) -> None: ...

    @abstractmethod
    async def submit_login_code(self, code: str) -> LoginStep: ...

    @abstractmethod
    async def submit_password(self, password: str) -> LoginStep: ...

    @abstractmethod
    def export_session(self) -> str: ...

    @abstractmethod
    async def log_out(self) -> None: ...

    # --- reading ----------------------------------------------------------
    @abstractmethod
    async def list_channels(self) -> list[TelegramChannel]: ...

    @abstractmethod
    async def start(self, channel_ids: Sequence[str], on_message: MessageHandler) -> None:
        """Begin listening; ``on_message`` is awaited for every new message."""

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def fetch_history(self, channel_id: str, limit: int = 100) -> list[InboundMessage]: ...

    async def fetch_between(
        self, channel_id: str, start: datetime, end: datetime, limit: int = 5000
    ) -> list[InboundMessage]:
        """Messages sent in [start, end), oldest first (used by Replay)."""
        msgs = await self.fetch_history(channel_id, limit)
        return [m for m in msgs if start <= m.sent_at < end]

    # --- acting as the user (opt-in helpers) -------------------------------
    async def create_bot(self, name: str, username: str) -> str:
        """Ask @BotFather for a new bot; returns its token."""
        raise FeatureDisabledError("Log in to Telegram first.")

    async def send_text(self, peer: str, text: str) -> None:
        """Send a message as the logged-in user (e.g. ``/start`` to the new bot)."""
        raise FeatureDisabledError("Log in to Telegram first.")
