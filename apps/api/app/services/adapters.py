"""Holds the active adapter implementations and builds them from settings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.adapters.base import AdapterHealth
from app.adapters.broker import BrokerAdapter, DisabledBrokerAdapter
from app.adapters.llm import DisabledLLMAdapter, LLMAdapter
from app.adapters.market_data import DisabledMarketDataAdapter, MarketDataAdapter
from app.adapters.telegram import DisabledTelegramAdapter, TelegramAdapter
from app.core.config import Settings


@dataclass(frozen=True)
class AdapterRegistry:
    broker: BrokerAdapter
    market_data: MarketDataAdapter
    telegram: TelegramAdapter
    llm: LLMAdapter

    @classmethod
    def from_settings(cls, settings: Settings) -> AdapterRegistry:
        # Phase 0: every integration is a disabled stub regardless of settings.
        # Later phases select real implementations here based on ``settings``.
        del settings
        return cls(
            broker=DisabledBrokerAdapter(),
            market_data=DisabledMarketDataAdapter(),
            telegram=DisabledTelegramAdapter(),
            llm=DisabledLLMAdapter(),
        )

    async def health(self) -> dict[str, AdapterHealth]:
        names = ("broker", "market_data", "telegram", "llm")
        results = await asyncio.gather(*(getattr(self, n).health() for n in names))
        return dict(zip(names, results, strict=True))
