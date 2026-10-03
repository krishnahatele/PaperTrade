"""Holds the active adapter implementations.

Adapters whose configuration lives in the database (Telegram, Kite, LLM) are
owned by their services and exposed here through getters, so the registry
always reports the current implementation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.adapters.base import AdapterHealth
from app.adapters.broker import BrokerAdapter, DisabledBrokerAdapter
from app.adapters.llm import DisabledLLMAdapter, LLMAdapter
from app.adapters.market_data import DisabledMarketDataAdapter, MarketDataAdapter
from app.adapters.telegram import DisabledTelegramAdapter, TelegramAdapter
from app.core.config import Settings


class AdapterRegistry:
    def __init__(
        self,
        *,
        broker: Callable[[], BrokerAdapter],
        market_data: Callable[[], MarketDataAdapter],
        telegram: Callable[[], TelegramAdapter],
        llm: Callable[[], LLMAdapter],
        health_overrides: dict[str, Callable[[], Awaitable[AdapterHealth]]] | None = None,
    ) -> None:
        self._health_overrides = health_overrides or {}
        self._broker = broker
        self._market_data = market_data
        self._telegram = telegram
        self._llm = llm

    @classmethod
    def from_settings(cls, settings: Settings) -> AdapterRegistry:
        """All-disabled registry (used by tests and as a safe default)."""
        del settings
        b, m, t, lm = (
            DisabledBrokerAdapter(),
            DisabledMarketDataAdapter(),
            DisabledTelegramAdapter(),
            DisabledLLMAdapter(),
        )
        return cls(broker=lambda: b, market_data=lambda: m, telegram=lambda: t, llm=lambda: lm)

    @property
    def broker(self) -> BrokerAdapter:
        return self._broker()

    @property
    def market_data(self) -> MarketDataAdapter:
        return self._market_data()

    @property
    def telegram(self) -> TelegramAdapter:
        return self._telegram()

    @property
    def llm(self) -> LLMAdapter:
        return self._llm()

    async def health(self) -> dict[str, AdapterHealth]:
        names = ("broker", "market_data", "telegram", "llm")
        results = await asyncio.gather(
            *(
                self._health_overrides[n]()
                if n in self._health_overrides
                else getattr(self, n).health()
                for n in names
            )
        )
        return dict(zip(names, results, strict=True))
