"""Owns the Telegram session lifecycle and turns channel posts into RawMessages."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.telegram import (
    DisabledTelegramAdapter,
    InboundMessage,
    LoginStep,
    TelegramAdapter,
    TelegramChannel,
)
from app.core.errors import FeatureDisabledError, NotFoundError
from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.models import RawMessage, SignalSource
from app.models.enums import RawMessageStatus, SignalSourceKind
from app.services.secrets import SecretName as N
from app.services.secrets import SecretStore

log = get_logger("marketos.telegram")

AdapterFactory = Callable[[int, str, str | None], TelegramAdapter]


def build_telethon_adapter(api_id: int, api_hash: str, session: str | None) -> TelegramAdapter:
    from app.adapters.telegram.telethon_adapter import TelethonTelegramAdapter

    return TelethonTelegramAdapter(api_id, api_hash, session)


class TelegramStatus(BaseModel):
    configured: bool
    authorized: bool
    listening: bool
    channels: int
    login_step: LoginStep | None
    messages_received: int
    last_message_at: datetime | None
    last_error: str | None


class TelegramService:
    def __init__(
        self,
        secrets: SecretStore,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        factory: AdapterFactory = build_telethon_adapter,
    ) -> None:
        self.secrets = secrets
        self.sf = session_factory
        self.bus = bus
        self.factory = factory
        self.adapter: TelegramAdapter = DisabledTelegramAdapter()
        self.configured = False
        self.authorized = False
        self.listening_channels: list[str] = []
        self.login_step: LoginStep | None = None
        self.messages_received = 0
        self.last_message_at: datetime | None = None
        self.last_error: str | None = None
        self._lock = asyncio.Lock()

    # --- lifecycle --------------------------------------------------------
    async def reload(self) -> None:
        """Rebuild the adapter from stored credentials (and session, if any)."""
        async with self._lock:
            await self._close_adapter()
            v = await self.secrets.get_many(
                N.TELEGRAM_API_ID, N.TELEGRAM_API_HASH, N.TELEGRAM_SESSION
            )
            api_id, api_hash, session = (
                v[N.TELEGRAM_API_ID],
                v[N.TELEGRAM_API_HASH],
                v[N.TELEGRAM_SESSION],
            )
            self.login_step = None
            self.listening_channels = []
            self.authorized = False
            if not (api_id and api_hash):
                self.configured = False
                self.adapter = DisabledTelegramAdapter()
                return
            self.configured = True
            self.adapter = self.factory(int(api_id), api_hash, session)

    async def start_listening(self) -> None:
        """(Re)subscribe to every enabled Telegram source. Safe to call repeatedly."""
        async with self._lock:
            if not self.configured:
                return
            try:
                self.authorized = await self.adapter.is_authorized()
                if not self.authorized:
                    return
                ids = await self._enabled_channel_ids()
                if ids:
                    await self.adapter.start(ids, self.ingest)
                else:
                    await self.adapter.stop()
                self.listening_channels = ids
                self.last_error = None
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("telegram.start_failed")

    async def boot(self, catch_up_limit: int = 50) -> None:
        try:
            await self.reload()
            await self.start_listening()
            if self.listening_channels:
                await self.catch_up(catch_up_limit)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.exception("telegram.boot_failed")

    async def shutdown(self) -> None:
        async with self._lock:
            await self._close_adapter()

    async def _close_adapter(self) -> None:
        close = getattr(self.adapter, "close", None)
        try:
            await self.adapter.stop()
            if close is not None:
                await close()
        except Exception:
            log.warning("telegram.close_failed", exc_info=True)

    # --- login ------------------------------------------------------------
    def _require_configured(self) -> None:
        if not self.configured:
            raise FeatureDisabledError(
                "Save your Telegram API ID, API hash and phone number in Settings first."
            )

    async def begin_login(self) -> LoginStep:
        phone = await self.secrets.get(N.TELEGRAM_PHONE)
        if not phone:
            raise FeatureDisabledError("Save your Telegram phone number in Settings first.")
        await self.secrets.delete(N.TELEGRAM_SESSION)
        await self.reload()
        self._require_configured()
        await self.adapter.send_login_code(phone)
        self.login_step = LoginStep.CODE
        return self.login_step

    async def submit_code(self, code: str) -> LoginStep:
        self._require_configured()
        step = await self.adapter.submit_login_code(code.strip().replace(" ", ""))
        return await self._after_step(step)

    async def submit_password(self, password: str) -> LoginStep:
        self._require_configured()
        step = await self.adapter.submit_password(password)
        return await self._after_step(step)

    async def _after_step(self, step: LoginStep) -> LoginStep:
        self.login_step = None if step is LoginStep.DONE else step
        if step is LoginStep.DONE:
            self.authorized = True
            self.last_error = None
            await self.secrets.put(N.TELEGRAM_SESSION, self.adapter.export_session())
            await self.bus.publish(
                Event(
                    type=EventType.INTEGRATION_UPDATED,
                    aggregate_type="integration",
                    payload={"integration": "telegram", "action": "logged_in", "fields": []},
                )
            )
            await self.start_listening()
        return step

    async def logout(self) -> None:
        try:
            await self.adapter.log_out()
        finally:
            await self.secrets.delete(N.TELEGRAM_SESSION)
            await self.reload()

    # --- reading ----------------------------------------------------------
    async def list_channels(self) -> list[TelegramChannel]:
        self._require_configured()
        return await self.adapter.list_channels()

    async def backfill(self, source_id: uuid.UUID, limit: int) -> int:
        async with self.sf() as s:
            source = await s.get(SignalSource, source_id)
        if source is None or source.kind is not SignalSourceKind.TELEGRAM or not source.external_id:
            raise NotFoundError("Telegram source not found")
        self._require_configured()
        messages = await self.adapter.fetch_history(source.external_id, limit)
        count = 0
        for m in messages:
            if await self._store(source.id, m):
                count += 1
        return count

    async def catch_up(self, limit: int = 50) -> int:
        """Store messages posted while the app was offline (deduplicated)."""
        async with self.sf() as s:
            sources = list(
                await s.scalars(
                    select(SignalSource).where(
                        SignalSource.kind == SignalSourceKind.TELEGRAM,
                        SignalSource.is_enabled.is_(True),
                        SignalSource.external_id.is_not(None),
                    )
                )
            )
        stored = 0
        for src in sources:
            try:
                stored += await self.backfill(src.id, limit)
            except Exception:
                log.warning("telegram.catch_up_failed", source=str(src.id), exc_info=True)
        log.info("telegram.caught_up", stored=stored, sources=len(sources))
        return stored

    async def ingest(self, message: InboundMessage) -> None:
        """Handler for live messages from the adapter."""
        async with self.sf() as s:
            source_id = await s.scalar(
                select(SignalSource.id).where(
                    SignalSource.kind == SignalSourceKind.TELEGRAM,
                    SignalSource.external_id == message.channel_id,
                    SignalSource.is_enabled.is_(True),
                )
            )
        if source_id is None:
            return
        await self._store(source_id, message)

    async def _store(self, source_id: uuid.UUID, m: InboundMessage) -> bool:
        """Insert a raw message; returns False if it was already stored (dedupe)."""
        payload = {
            **m.raw,
            "reply_to_message_id": m.reply_to_message_id,
            "channel_id": m.channel_id,
        }
        async with self.sf() as s:
            new_id = await s.scalar(
                insert(RawMessage)
                .values(
                    id=uuid.uuid4(),
                    source_id=source_id,
                    external_message_id=m.message_id,
                    content=m.text,
                    payload=payload,
                    received_at=m.sent_at,
                    status=RawMessageStatus.PENDING,
                )
                .on_conflict_do_nothing(index_elements=["source_id", "external_message_id"])
                .returning(RawMessage.id)
            )
            await s.commit()
        if new_id is None:
            return False
        self.messages_received += 1
        self.last_message_at = datetime.now(UTC)
        await self.bus.publish(
            Event(
                type=EventType.RAW_MESSAGE_RECEIVED,
                aggregate_type="raw_message",
                aggregate_id=new_id,
                payload={"source_id": str(source_id), "preview": m.text[:120]},
            )
        )
        return True

    async def _enabled_channel_ids(self) -> list[str]:
        async with self.sf() as s:
            rows = await s.scalars(
                select(SignalSource.external_id).where(
                    SignalSource.kind == SignalSourceKind.TELEGRAM,
                    SignalSource.is_enabled.is_(True),
                    SignalSource.external_id.is_not(None),
                )
            )
            return [r for r in rows if r]

    async def health(self) -> AdapterHealth:
        """Cheap health from cached state (no network round-trip)."""
        name = self.adapter.name
        if not self.configured:
            return AdapterHealth(
                name=name,
                state=AdapterState.NOT_CONFIGURED,
                detail="Add API ID, API hash and phone number in Settings.",
            )
        if self.last_error:
            return AdapterHealth(name=name, state=AdapterState.ERROR, detail=self.last_error)
        if not self.authorized:
            return AdapterHealth(
                name=name,
                state=AdapterState.NOT_CONFIGURED,
                detail="Log in to Telegram in Settings.",
            )
        detail = (
            f"Listening to {len(self.listening_channels)} channel(s)"
            if self.listening_channels
            else "Logged in; no enabled channels"
        )
        return AdapterHealth(name=name, state=AdapterState.READY, detail=detail)

    async def status(self) -> TelegramStatus:
        if self.configured:
            try:
                self.authorized = await asyncio.wait_for(self.adapter.is_authorized(), 20)
            except Exception as exc:
                self.last_error = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
        return TelegramStatus(
            configured=self.configured,
            authorized=self.authorized,
            listening=bool(self.listening_channels),
            channels=len(self.listening_channels),
            login_step=self.login_step,
            messages_received=self.messages_received,
            last_message_at=self.last_message_at,
            last_error=self.last_error,
        )
