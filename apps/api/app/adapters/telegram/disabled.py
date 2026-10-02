from __future__ import annotations

from collections.abc import Sequence

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.telegram.base import InboundMessage, MessageHandler, TelegramAdapter
from app.core.errors import FeatureDisabledError

_MSG = "Telegram ingestion is not available in Phase 0."


class DisabledTelegramAdapter(TelegramAdapter):
    name = "disabled"

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.DISABLED, detail=_MSG)

    async def start(self, channel_ids: Sequence[str], on_message: MessageHandler) -> None:
        raise FeatureDisabledError(_MSG)

    async def stop(self) -> None:
        return None

    async def fetch_history(self, channel_id: str, limit: int = 100) -> list[InboundMessage]:
        raise FeatureDisabledError(_MSG)
