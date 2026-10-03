"""Composition root: builds long-lived application dependencies once."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.adapters.broker import DisabledBrokerAdapter
from app.adapters.llm import DisabledLLMAdapter
from app.adapters.market_data import DisabledMarketDataAdapter
from app.core.config import Settings
from app.core.crypto import SecretBox, load_master_key
from app.core.logging import get_logger
from app.db.session import Database
from app.events import InMemoryEventBus
from app.events.bus import WILDCARD
from app.events.store import EventStore
from app.services.adapters import AdapterRegistry
from app.services.auth import AuthService, LoginRateLimiter
from app.services.runtime import RuntimeStore
from app.services.secrets import SecretStore
from app.services.telegram import TelegramService

log = get_logger("marketos")


@dataclass
class Container:
    settings: Settings
    db: Database
    bus: InMemoryEventBus
    box: SecretBox
    secrets: SecretStore
    runtime: RuntimeStore
    telegram: TelegramService
    adapters: AdapterRegistry
    login_limiter: LoginRateLimiter = field(default_factory=LoginRateLimiter)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set)

    @classmethod
    def build(cls, settings: Settings) -> Container:
        db = Database(settings)
        bus = InMemoryEventBus()
        bus.subscribe(WILDCARD, EventStore(db.session_factory))
        box = SecretBox(load_master_key(settings))
        secrets = SecretStore(db.session_factory, box)
        telegram = TelegramService(secrets, db.session_factory, bus)

        broker, market_data, llm = (
            DisabledBrokerAdapter(),
            DisabledMarketDataAdapter(),
            DisabledLLMAdapter(),
        )
        adapters = AdapterRegistry(
            broker=lambda: broker,
            market_data=lambda: market_data,
            telegram=lambda: telegram.adapter,
            llm=lambda: llm,
            health_overrides={"telegram": telegram.health},
        )
        return cls(
            settings=settings,
            db=db,
            bus=bus,
            box=box,
            secrets=secrets,
            runtime=RuntimeStore(db.session_factory),
            telegram=telegram,
            adapters=adapters,
        )

    def auth(self) -> AuthService:
        return AuthService(
            self.secrets,
            self.runtime,
            self.box,
            self.settings.auth_token_ttl_hours,
            self.login_limiter,
        )

    def spawn(self, coro: object, name: str) -> None:
        """Run a background coroutine, keeping a reference and logging failures."""
        task: asyncio.Task[None] = asyncio.create_task(coro, name=name)  # type: ignore[arg-type]
        self._tasks.add(task)

        def _done(t: asyncio.Task[None]) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.error("background.failed", task=name, error=repr(t.exception()))

        task.add_done_callback(_done)

    async def start_background(self) -> None:
        if not self.settings.background_services:
            return
        self.spawn(self.telegram.boot(), "telegram.boot")

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.telegram.shutdown()
        await self.db.dispose()
