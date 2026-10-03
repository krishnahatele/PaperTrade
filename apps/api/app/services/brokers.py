"""Broker connections: credentials (encrypted), connection tests, Dhan token
renewal, and building adapters for whichever broker the user picked.

Read-only use today (profile, funds, positions, prices, candles). Order
placement through these adapters is not wired into the trading engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from app.adapters.broker.base import BrokerAdapter, BrokerFunds, BrokerPosition, BrokerProfile
from app.adapters.broker.dhan import DhanBrokerAdapter, DhanClient
from app.adapters.broker.providers import BROKERS, BrokerInfo, BrokerProvider
from app.core.errors import FeatureDisabledError, InvalidInputError, MarketOSError
from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.services.kite import KiteService
from app.services.runtime import BrokerRuntime, RuntimeStore
from app.services.secrets import SecretStore

log = get_logger("marketos.brokers")

DHAN_RENEW_AFTER = timedelta(hours=20)


class FieldStatus(BaseModel):
    name: str
    set: bool
    hint: str | None = None


class BrokerStatus(BaseModel):
    info: BrokerInfo
    configured: bool
    session_active: bool
    fields: list[FieldStatus]
    selected: bool


class ConnectionTest(BaseModel):
    ok: bool
    provider: BrokerProvider
    profile: BrokerProfile | None = None
    funds: BrokerFunds | None = None
    positions: list[BrokerPosition] = []
    error: str | None = None
    notes: list[str] = []


def _mask(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    return "•" * 4 + value[-keep:] if len(value) > keep else "•" * len(value)


class BrokerService:
    def __init__(
        self,
        secrets: SecretStore,
        runtime: RuntimeStore,
        bus: EventBus,
        kite: KiteService,
        dhan_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.secrets = secrets
        self.runtime = runtime
        self.bus = bus
        self.kite = kite
        self.dhan_transport = dhan_transport
        self.kite_factory: Callable[[str, str], BrokerAdapter] = _kite_adapter

    # ------------------------------------------------------------ credentials
    def info(self, provider: BrokerProvider) -> BrokerInfo:
        return BROKERS[provider]

    async def values(self, provider: BrokerProvider) -> dict[str, str | None]:
        return {f.name: await self.secrets.get(f.secret_name) for f in BROKERS[provider].fields}

    async def save(self, provider: BrokerProvider, values: dict[str, str]) -> list[str]:
        info = BROKERS[provider]
        if not info.available:
            raise FeatureDisabledError(f"{info.label} is not supported yet.")
        by_name = {f.name: f for f in info.fields}
        unknown = set(values) - set(by_name)
        if unknown:
            raise InvalidInputError(
                f"Unknown field(s) for {info.label}: {', '.join(sorted(unknown))}"
            )
        changed = []
        for name, value in values.items():
            v = value.strip()
            if v:
                await self.secrets.put(by_name[name].secret_name, v)
                changed.append(name)
        if provider is BrokerProvider.DHAN and "access_token" in changed:
            await self.runtime.update(BrokerRuntime, dhan_token_saved_at=datetime.now(UTC))
        if provider is BrokerProvider.KITE and changed:
            await self.kite.logout()  # new key/secret invalidate today's session
        if changed:
            await self._audit(provider, "updated", changed)
        return changed

    async def clear(self, provider: BrokerProvider) -> None:
        info = BROKERS[provider]
        await self.secrets.delete(*[f.secret_name for f in info.fields])
        if provider is BrokerProvider.KITE:
            await self.kite.logout()
        await self._audit(provider, "cleared", [])

    async def status(self) -> list[BrokerStatus]:
        selected = (await self.runtime.get(BrokerRuntime)).primary
        kite = await self.kite.status()
        out = []
        for info in BROKERS.values():
            vals = await self.values(info.id) if info.fields else {}
            fields = [
                FieldStatus(
                    name=f.name,
                    set=bool(vals.get(f.name)),
                    hint=(vals.get(f.name) if not f.secret else _mask(vals.get(f.name))),
                )
                for f in info.fields
            ]
            configured = all(x.set for x in fields) if fields else info.available
            session = {
                BrokerProvider.PAPER: True,
                BrokerProvider.KITE: kite.session_active,
                BrokerProvider.DHAN: configured,
            }.get(info.id, False)
            out.append(
                BrokerStatus(
                    info=info,
                    configured=configured,
                    session_active=session,
                    fields=fields,
                    selected=info.id is selected,
                )
            )
        return out

    # --------------------------------------------------------------- adapters
    async def dhan_client(self) -> DhanClient | None:
        v = await self.values(BrokerProvider.DHAN)
        if not v.get("client_id") or not v.get("access_token"):
            return None
        return DhanClient(str(v["client_id"]), str(v["access_token"]), self.dhan_transport)

    async def adapter(self, provider: BrokerProvider) -> BrokerAdapter:
        if provider is BrokerProvider.DHAN:
            client = await self.dhan_client()
            if client is None:
                raise FeatureDisabledError("Save your Dhan client ID and access token first.")
            return DhanBrokerAdapter(client)
        if provider is BrokerProvider.KITE:
            creds = await self.kite.credentials()
            if creds is None:
                raise FeatureDisabledError("Log in to Kite first (Settings → Zerodha Kite).")
            return self.kite_factory(*creds)
        raise FeatureDisabledError(f"{BROKERS[provider].label} has no broker connection.")

    async def test(self, provider: BrokerProvider) -> ConnectionTest:
        """Read-only check: profile, funds and positions. Never places orders."""
        info = BROKERS[provider]
        notes = []
        if info.static_ip_required:
            notes.append(
                "Placing real orders through the API needs a static IP registered with the "
                "broker (SEBI rule from April 2026). Reading data works from anywhere."
            )
        adapter: BrokerAdapter | None = None
        try:
            adapter = await self.adapter(provider)
            profile = await adapter.profile()
            funds = await adapter.funds()
            positions = await adapter.get_positions()
        except MarketOSError as exc:
            return ConnectionTest(ok=False, provider=provider, error=exc.message, notes=notes)
        finally:
            if isinstance(adapter, DhanBrokerAdapter):
                await adapter.client.close()
        await self._audit(provider, "tested", [])
        return ConnectionTest(
            ok=True,
            provider=provider,
            profile=profile,
            funds=funds,
            positions=positions,
            notes=notes,
        )

    async def renew_dhan_if_due(self, force: bool = False) -> bool:
        """Dhan tokens live 24 h; renew one that is ~20 h old so it never lapses."""
        rt = await self.runtime.get(BrokerRuntime)
        saved = rt.dhan_token_saved_at
        if not force and (saved is None or datetime.now(UTC) - saved < DHAN_RENEW_AFTER):
            return False
        client = await self.dhan_client()
        if client is None:
            return False
        try:
            token = await client.renew_token()
        except MarketOSError as exc:
            log.warning("dhan.renew_failed", error=exc.message)
            return False
        finally:
            await client.close()
        await self.secrets.put(BROKERS[BrokerProvider.DHAN].fields[1].secret_name, token)
        await self.runtime.update(BrokerRuntime, dhan_token_saved_at=datetime.now(UTC))
        await self._audit(BrokerProvider.DHAN, "token_renewed", [])
        return True

    async def _audit(self, provider: BrokerProvider, action: str, fields: list[str]) -> None:
        await self.bus.publish(
            Event(
                type=EventType.INTEGRATION_UPDATED,
                aggregate_type="integration",
                payload={
                    "integration": f"broker.{provider.value}",
                    "action": action,
                    "fields": fields,
                },
            )
        )


def _kite_adapter(api_key: str, access_token: str) -> BrokerAdapter:
    from app.adapters.broker.kite import KiteBrokerAdapter

    return KiteBrokerAdapter(api_key, access_token)
