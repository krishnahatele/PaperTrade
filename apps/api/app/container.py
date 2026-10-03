"""Composition root: builds long-lived application dependencies once."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.broker import DisabledBrokerAdapter
from app.core.config import Settings
from app.core.crypto import SecretBox, load_master_key
from app.core.logging import get_logger
from app.db.session import Database
from app.events import EventType, InMemoryEventBus
from app.events.bus import WILDCARD
from app.events.store import EventStore
from app.services.adapters import AdapterRegistry
from app.services.auth import AuthService, LoginRateLimiter
from app.services.instruments import InstrumentService
from app.services.kite import KiteService
from app.services.llm import LLMService
from app.services.market_data import MarketDataService
from app.services.runtime import RuntimeStore
from app.services.secrets import SecretStore
from app.services.signal_pipeline import SignalPipeline
from app.services.telegram import TelegramService
from app.services.trading import TradingEngine

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
    llm: LLMService
    instruments: InstrumentService
    pipeline: SignalPipeline
    kite: KiteService
    market: MarketDataService
    engine: TradingEngine
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
        runtime = RuntimeStore(db.session_factory)
        telegram = TelegramService(secrets, db.session_factory, bus)
        llm = LLMService(secrets, runtime)
        instruments = InstrumentService(db.session_factory, bus)

        kite = KiteService(secrets, bus)
        market = MarketDataService(kite)
        engine = TradingEngine(db.session_factory, bus, runtime, market)

        async def broker_health() -> AdapterHealth:
            return AdapterHealth(
                name="paper",
                state=AdapterState.READY,
                detail="Paper trading: simulated fills at live/manual prices",
            )

        broker = DisabledBrokerAdapter()  # live routing is not enabled in this build
        adapters = AdapterRegistry(
            broker=lambda: broker,
            market_data=lambda: market.adapter,
            telegram=lambda: telegram.adapter,
            llm=lambda: llm.adapter,
            health_overrides={
                "telegram": telegram.health,
                "llm": llm.health,
                "market_data": market.health,
                "broker": broker_health,
            },
        )
        container = cls(
            settings=settings,
            db=db,
            bus=bus,
            box=box,
            secrets=secrets,
            runtime=runtime,
            telegram=telegram,
            llm=llm,
            instruments=instruments,
            pipeline=SignalPipeline(db.session_factory, bus, runtime, llm, instruments),
            kite=kite,
            market=market,
            engine=engine,
            adapters=adapters,
        )
        if settings.background_services:
            container.pipeline.spawn = container.spawn
            container.engine.spawn = container.spawn
        bus.subscribe(EventType.RAW_MESSAGE_RECEIVED, container.pipeline.on_raw_message)
        bus.subscribe(EventType.SIGNAL_CREATED, container.engine.on_signal_event)
        bus.subscribe(EventType.SIGNAL_STATUS_CHANGED, container.engine.on_signal_event)
        return container

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
        try:
            await self.llm.reload()
            await self.market.reload()
            await self.engine.ensure_paper_account()
        except Exception:
            log.warning("startup.reload_failed", exc_info=True)
        if not self.settings.background_services:
            return
        self.spawn(self.telegram.boot(), "telegram.boot")
        self.spawn(self.engine.run_forever(), "trading.engine")

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.telegram.shutdown()
        await self.db.dispose()
