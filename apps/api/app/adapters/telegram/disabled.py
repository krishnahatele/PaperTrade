from __future__ import annotations

from collections.abc import Sequence

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.telegram.base import (
    InboundMessage,
    LoginStep,
    MessageHandler,
    TelegramAdapter,
    TelegramChannel,
)
from app.core.errors import FeatureDisabledError

_MSG = "Telegram is not configured. Add API ID, API hash and phone number in Settings."


class DisabledTelegramAdapter(TelegramAdapter):
    name = "disabled"

    def __init__(self, detail: str = _MSG, state: AdapterState = AdapterState.NOT_CONFIGURED):
        self._detail = detail
        self._state = state

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=self._state, detail=self._detail)

    async def is_authorized(self) -> bool:
        return False

    async def send_login_code(self, phone: str) -> None:
        raise FeatureDisabledError(self._detail)

    async def submit_login_code(self, code: str) -> LoginStep:
        raise FeatureDisabledError(self._detail)

    async def submit_password(self, password: str) -> LoginStep:
        raise FeatureDisabledError(self._detail)

    def export_session(self) -> str:
        raise FeatureDisabledError(self._detail)

    async def log_out(self) -> None:
        return None

    async def list_channels(self) -> list[TelegramChannel]:
        raise FeatureDisabledError(self._detail)

    async def start(self, channel_ids: Sequence[str], on_message: MessageHandler) -> None:
        raise FeatureDisabledError(self._detail)

    async def stop(self) -> None:
        return None

    async def fetch_history(self, channel_id: str, limit: int = 100) -> list[InboundMessage]:
        raise FeatureDisabledError(self._detail)
