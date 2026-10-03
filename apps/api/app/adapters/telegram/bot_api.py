"""Minimal Telegram Bot API client (https://core.telegram.org/bots/api) over httpx.

Used for the MarketOS control bot: notifications with inline buttons, a
persistent keyboard, and long-polling for button presses / commands.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import MarketOSError

API = "https://api.telegram.org"


class BotApiError(MarketOSError):
    status_code = 502
    code = "telegram_bot_error"


class BotApi:
    def __init__(
        self,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = API,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url}/bot{token}", timeout=40.0, transport=transport
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def call(self, method: str, **params: Any) -> Any:
        body = {k: v for k, v in params.items() if v is not None}
        try:
            r = await self._http.post(f"/{method}", json=body)
        except httpx.HTTPError as exc:
            raise BotApiError(f"Cannot reach Telegram: {type(exc).__name__}") from exc
        try:
            data = r.json()
        except ValueError as exc:
            raise BotApiError(f"Telegram returned {r.status_code}") from exc
        if not data.get("ok"):
            desc = data.get("description") or r.reason_phrase
            if r.status_code == 401:
                raise BotApiError("Telegram rejected the bot token. Check it in Settings.")
            raise BotApiError(f"Telegram: {desc}")
        return data.get("result")

    async def get_me(self) -> dict[str, Any]:
        return dict(await self.call("getMe"))

    async def get_updates(self, offset: int | None, wait: int = 25) -> list[dict[str, Any]]:
        """Long poll: Telegram holds the request up to ``wait`` seconds."""
        return list(
            await self.call(
                "getUpdates",
                offset=offset,
                timeout=wait,
                allowed_updates=["message", "callback_query"],
            )
            or []
        )

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> dict[str, Any]:
        return dict(
            await self.call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_notification=silent or None,
                link_preview_options={"is_disabled": True},
            )
        )

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        try:
            await self.call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup or {"inline_keyboard": []},
                link_preview_options={"is_disabled": True},
            )
        except BotApiError as exc:
            if "message is not modified" not in exc.message:
                raise

    async def answer_callback(self, callback_id: str, text: str, alert: bool = False) -> None:
        await self.call(
            "answerCallbackQuery", callback_query_id=callback_id, text=text[:190], show_alert=alert
        )

    async def pin(self, chat_id: int, message_id: int) -> None:
        await self.call(
            "pinChatMessage", chat_id=chat_id, message_id=message_id, disable_notification=True
        )

    async def set_commands(self, commands: list[tuple[str, str]]) -> None:
        await self.call(
            "setMyCommands",
            commands=[{"command": c, "description": d} for c, d in commands],
        )
