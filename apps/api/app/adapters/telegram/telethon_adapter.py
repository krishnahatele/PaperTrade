"""Telethon-backed TelegramAdapter (MTProto user client)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC
from typing import Any

from telethon import TelegramClient, events, utils
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.telegram.base import (
    InboundMessage,
    LoginStep,
    MessageHandler,
    TelegramAdapter,
    TelegramChannel,
)
from app.core.errors import InvalidInputError, MarketOSError
from app.core.logging import get_logger

log = get_logger("marketos.telegram")


class TelegramRateLimitedError(MarketOSError):
    status_code = 429
    code = "telegram_rate_limited"


class TelegramUnavailableError(MarketOSError):
    status_code = 503
    code = "telegram_unavailable"


CONNECT_TIMEOUT = 15.0


class TelegramLoginError(MarketOSError):
    status_code = 400
    code = "telegram_login_failed"


def _to_inbound(msg: Any) -> InboundMessage | None:
    text = (getattr(msg, "message", None) or "").strip()
    if not text:
        return None
    reply = getattr(msg, "reply_to", None)
    reply_id = getattr(reply, "reply_to_msg_id", None) if reply else None
    sent = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC)
    return InboundMessage(
        channel_id=str(utils.get_peer_id(msg.peer_id)),
        message_id=str(msg.id),
        text=text,
        sent_at=sent,
        reply_to_message_id=str(reply_id) if reply_id else None,
        raw={
            "views": getattr(msg, "views", None),
            "edit_date": msg.edit_date.isoformat() if getattr(msg, "edit_date", None) else None,
            "has_media": bool(getattr(msg, "media", None)),
        },
    )


class TelethonTelegramAdapter(TelegramAdapter):
    name = "telethon"

    def __init__(self, api_id: int, api_hash: str, session: str | None = None) -> None:
        self._client = TelegramClient(
            StringSession(session or None),
            api_id,
            api_hash,
            device_model="MarketOS",
            app_version="MarketOS",
            receive_updates=True,
            connection_retries=3,
            timeout=10,
            auto_reconnect=True,
        )
        self._phone: str | None = None
        self._phone_code_hash: str | None = None
        self._handler: Any = None
        self._watched: set[str] = set()
        self._last_error: str | None = None

    async def _connect(self) -> None:
        if not self._client.is_connected():
            try:
                await asyncio.wait_for(self._client.connect(), CONNECT_TIMEOUT)
            except (TimeoutError, OSError) as exc:
                raise TelegramUnavailableError(
                    "Cannot reach Telegram servers. Check network connectivity."
                ) from exc

    async def health(self) -> AdapterHealth:
        try:
            authorized = await asyncio.wait_for(self.is_authorized(), CONNECT_TIMEOUT + 2)
        except Exception as exc:
            detail = exc.message if isinstance(exc, MarketOSError) else repr(exc)
            return AdapterHealth(name=self.name, state=AdapterState.ERROR, detail=detail)
        if not authorized:
            return AdapterHealth(
                name=self.name,
                state=AdapterState.NOT_CONFIGURED,
                detail="Credentials saved. Log in from Settings to start reading channels.",
            )
        detail = f"Listening to {len(self._watched)} channel(s)" if self._handler else "Idle"
        return AdapterHealth(name=self.name, state=AdapterState.READY, detail=detail)

    # --- login ------------------------------------------------------------
    async def is_authorized(self) -> bool:
        await self._connect()
        return bool(await self._client.is_user_authorized())

    async def send_login_code(self, phone: str) -> None:
        await self._connect()
        try:
            sent = await self._client.send_code_request(phone)
        except PhoneNumberInvalidError as exc:
            raise InvalidInputError("Telegram rejected the phone number.") from exc
        except FloodWaitError as exc:
            raise TelegramRateLimitedError(
                f"Telegram asks to wait {exc.seconds}s before another code."
            ) from exc
        self._phone = phone
        self._phone_code_hash = sent.phone_code_hash

    async def submit_login_code(self, code: str) -> LoginStep:
        if not self._phone or not self._phone_code_hash:
            raise TelegramLoginError("Request a login code first.")
        try:
            await self._client.sign_in(
                phone=self._phone, code=code, phone_code_hash=self._phone_code_hash
            )
        except SessionPasswordNeededError:
            return LoginStep.PASSWORD
        except (PhoneCodeInvalidError, PhoneCodeExpiredError) as exc:
            raise TelegramLoginError("The code is invalid or expired.") from exc
        except FloodWaitError as exc:
            raise TelegramRateLimitedError(f"Wait {exc.seconds}s and try again.") from exc
        return LoginStep.DONE

    async def submit_password(self, password: str) -> LoginStep:
        try:
            await self._client.sign_in(password=password)
        except PasswordHashInvalidError as exc:
            raise TelegramLoginError("Incorrect two-step verification password.") from exc
        except FloodWaitError as exc:
            raise TelegramRateLimitedError(f"Wait {exc.seconds}s and try again.") from exc
        return LoginStep.DONE

    def export_session(self) -> str:
        return str(StringSession.save(self._client.session))

    async def log_out(self) -> None:
        await self.stop()
        if self._client.is_connected():
            try:
                await self._client.log_out()
            finally:
                await self._client.disconnect()

    # --- reading ----------------------------------------------------------
    async def list_channels(self) -> list[TelegramChannel]:
        await self._connect()
        out: list[TelegramChannel] = []
        async for d in self._client.iter_dialogs():
            if not (d.is_channel or d.is_group):
                continue
            out.append(
                TelegramChannel(
                    id=str(d.id),
                    title=d.title or str(d.id),
                    username=getattr(d.entity, "username", None),
                    kind="group" if d.is_group else "channel",
                )
            )
        return out

    async def start(self, channel_ids: Sequence[str], on_message: MessageHandler) -> None:
        await self.stop()
        await self._connect()
        # Populate the entity cache so updates for these chats can be resolved.
        await self._client.get_dialogs()
        self._watched = set(channel_ids)

        async def handler(event: Any) -> None:
            if str(event.chat_id) not in self._watched:
                return
            inbound = _to_inbound(event.message)
            if inbound is None:
                return
            try:
                await on_message(inbound)
            except Exception:
                log.exception("telegram.handler_failed", channel_id=inbound.channel_id)

        self._client.add_event_handler(handler, events.NewMessage())
        self._handler = handler
        log.info("telegram.listening", channels=len(self._watched))

    async def stop(self) -> None:
        if self._handler is not None:
            self._client.remove_event_handler(self._handler)
            self._handler = None

    async def fetch_history(self, channel_id: str, limit: int = 100) -> list[InboundMessage]:
        await self._connect()
        entity = await self._client.get_input_entity(int(channel_id))
        out: list[InboundMessage] = []
        async for m in self._client.iter_messages(entity, limit=limit):
            inbound = _to_inbound(m)
            if inbound is not None:
                out.append(inbound)
        out.reverse()  # oldest first
        return out

    async def close(self) -> None:
        await self.stop()
        if self._client.is_connected():
            await self._client.disconnect()
