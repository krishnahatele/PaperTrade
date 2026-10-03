"""In-memory test doubles for external adapters."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.telegram import (
    InboundMessage,
    LoginStep,
    MessageHandler,
    TelegramAdapter,
    TelegramChannel,
)
from app.adapters.telegram.telethon_adapter import TelegramLoginError

CHANNELS = [
    TelegramChannel(id="-1001", title="Alpha Calls", username="alpha", kind="channel"),
    TelegramChannel(id="-1002", title="Beta Group", username=None, kind="group"),
]


class FakeTelegram(TelegramAdapter):
    name = "fake"
    instances: list[FakeTelegram] = []  # noqa: RUF012

    def __init__(self, api_id: int, api_hash: str, session: str | None) -> None:
        self.api_id, self.api_hash, self.session = api_id, api_hash, session
        self.authorized = session == "SESSION-OK"
        self.code_sent_to: str | None = None
        self.needs_password = False
        self.handler: MessageHandler | None = None
        self.watched: list[str] = []
        self.history: dict[str, list[InboundMessage]] = {}
        FakeTelegram.instances.append(self)

    async def health(self) -> AdapterHealth:
        return AdapterHealth(
            name=self.name,
            state=AdapterState.READY if self.authorized else AdapterState.NOT_CONFIGURED,
        )

    async def is_authorized(self) -> bool:
        return self.authorized

    async def send_login_code(self, phone: str) -> None:
        self.code_sent_to = phone

    async def submit_login_code(self, code: str) -> LoginStep:
        if code != "12345":
            raise TelegramLoginError("The code is invalid or expired.")
        if self.needs_password:
            return LoginStep.PASSWORD
        self.authorized = True
        return LoginStep.DONE

    async def submit_password(self, password: str) -> LoginStep:
        if password != "2fa-pass":
            raise TelegramLoginError("Incorrect two-step verification password.")
        self.authorized = True
        return LoginStep.DONE

    def export_session(self) -> str:
        return "SESSION-OK"

    async def log_out(self) -> None:
        self.authorized = False

    async def list_channels(self) -> list[TelegramChannel]:
        return CHANNELS

    async def start(self, channel_ids: Sequence[str], on_message: MessageHandler) -> None:
        self.watched = list(channel_ids)
        self.handler = on_message

    async def stop(self) -> None:
        self.handler = None
        self.watched = []

    async def fetch_history(self, channel_id: str, limit: int = 100) -> list[InboundMessage]:
        return self.history.get(channel_id, [])[-limit:]

    async def push(self, channel_id: str, message_id: str, text: str) -> None:
        assert self.handler is not None, "not listening"
        if channel_id in self.watched:
            await self.handler(msg(channel_id, message_id, text))


def msg(channel_id: str, message_id: str, text: str) -> InboundMessage:
    return InboundMessage(
        channel_id=channel_id, message_id=message_id, text=text, sent_at=datetime.now(UTC)
    )


# --- LLM -------------------------------------------------------------------
from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from app.adapters.llm import LLMAdapter, LLMRequest, LLMResponse  # noqa: E402


class FakeLLM(LLMAdapter):
    """Returns a canned structured response; records calls."""

    name = "fake-llm"

    def __init__(self, response: Mapping[str, Any] | None = None, fail: bool = False) -> None:
        self.response = dict(response or {})
        self.fail = fail
        self.calls: list[LLMRequest] = []

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.READY)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self.fail:
            raise RuntimeError("llm down")
        return LLMResponse(content="{}", model="fake", parsed=self.response)


# Sample of Kite's public instrument dump.
KITE_CSV = """\
instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
738561,2885,RELIANCE,RELIANCE INDUSTRIES,0,,0,0.05,1,EQ,NSE,NSE
408065,1594,INFY,INFOSYS,0,,0,0.05,1,EQ,NSE,NSE
256265,1001,NIFTY 50,NIFTY 50,0,,0,0,0,EQ,INDICES,NSE
12345601,48201,NIFTY2610824500CE,NIFTY,0,2099-01-08,24500,0.05,75,CE,NFO-OPT,NFO
12345602,48202,NIFTY2611524500CE,NIFTY,0,2099-01-15,24500,0.05,75,CE,NFO-OPT,NFO
12345603,48203,NIFTY2610824500PE,NIFTY,0,2099-01-08,24500,0.05,75,PE,NFO-OPT,NFO
12345604,48204,NIFTY2001024500CE,NIFTY,0,2020-01-02,24500,0.05,75,CE,NFO-OPT,NFO
12345605,48205,TATAMOTORS99JANFUT,TATAMOTORS,0,2099-01-29,0,0.05,550,FUT,NFO-FUT,NFO
12345606,48206,XYZ,XYZ,0,,0,0.05,1,EQ,CDS-X,NCO
"""
