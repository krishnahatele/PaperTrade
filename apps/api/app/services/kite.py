"""Kite Connect login: API key/secret -> daily access token (stored encrypted)."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

from app.core.errors import FeatureDisabledError, InvalidInputError
from app.events import Event, EventBus, EventType
from app.services.secrets import SecretName as N
from app.services.secrets import SecretStore


class KiteStatus(BaseModel):
    configured: bool
    session_active: bool
    user_id: str | None


def extract_request_token(value: str) -> str:
    """Accept either the bare request_token or the full redirect URL Kite sends you to."""
    v = value.strip()
    if v.startswith("http"):
        tokens = parse_qs(urlparse(v).query).get("request_token")
        if not tokens:
            raise InvalidInputError("That URL has no request_token in it.")
        v = tokens[0]
    if not v.isalnum() or not 8 <= len(v) <= 64:
        raise InvalidInputError("That doesn't look like a Kite request_token.")
    return v


class KiteService:
    def __init__(self, secrets: SecretStore, bus: EventBus) -> None:
        self.secrets = secrets
        self.bus = bus

    async def login_url(self) -> str:
        from kiteconnect import KiteConnect

        key = await self.secrets.get(N.KITE_API_KEY)
        if not key:
            raise FeatureDisabledError("Save your Kite API key and secret in Settings first.")
        return str(KiteConnect(api_key=key).login_url())

    async def create_session(self, request_token_or_url: str) -> KiteStatus:
        from kiteconnect import KiteConnect
        from kiteconnect import exceptions as kex

        token = extract_request_token(request_token_or_url)
        v = await self.secrets.get_many(N.KITE_API_KEY, N.KITE_API_SECRET)
        key, secret = v[N.KITE_API_KEY], v[N.KITE_API_SECRET]
        if not key or not secret:
            raise FeatureDisabledError("Save your Kite API key and secret in Settings first.")
        kite = KiteConnect(api_key=key, timeout=15)
        try:
            data = await asyncio.to_thread(kite.generate_session, token, secret)
        except kex.KiteException as exc:
            raise InvalidInputError(f"Kite rejected the login: {exc}") from exc
        await self.secrets.put(N.KITE_ACCESS_TOKEN, str(data["access_token"]))
        await self.secrets.put(N.KITE_USER_ID, str(data.get("user_id", "")))
        await self.bus.publish(
            Event(
                type=EventType.INTEGRATION_UPDATED,
                aggregate_type="integration",
                payload={"integration": "kite", "action": "logged_in", "fields": []},
            )
        )
        return await self.status()

    async def logout(self) -> None:
        await self.secrets.delete(N.KITE_ACCESS_TOKEN, N.KITE_USER_ID)

    async def credentials(self) -> tuple[str, str] | None:
        v = await self.secrets.get_many(N.KITE_API_KEY, N.KITE_ACCESS_TOKEN)
        key, token = v[N.KITE_API_KEY], v[N.KITE_ACCESS_TOKEN]
        return (key, token) if key and token else None

    async def status(self) -> KiteStatus:
        v = await self.secrets.get_many(
            N.KITE_API_KEY, N.KITE_API_SECRET, N.KITE_ACCESS_TOKEN, N.KITE_USER_ID
        )
        return KiteStatus(
            configured=bool(v[N.KITE_API_KEY] and v[N.KITE_API_SECRET]),
            session_active=bool(v[N.KITE_ACCESS_TOKEN]),
            user_id=v[N.KITE_USER_ID] or None,
        )
