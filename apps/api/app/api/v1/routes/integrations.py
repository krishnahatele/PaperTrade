"""Credential management. Secrets are write-only: the API only reports whether
each one is set (plus a masked hint), never the value."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep
from app.events import Event, EventType
from app.schemas.integrations import (
    IntegrationsStatus,
    KiteCredentials,
    KiteStatus,
    LLMCredentials,
    LLMStatus,
    SecretField,
    TelegramCredentials,
    TelegramStatus,
    mask,
)
from app.services.secrets import SecretName as N

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _field(value: str | None, *, hint: bool = True, keep: int = 4) -> SecretField:
    return SecretField(set=bool(value), hint=mask(value, keep) if hint else None)


@router.get("", response_model=IntegrationsStatus)
async def get_integrations(container: ContainerDep) -> IntegrationsStatus:
    v = await container.secrets.get_many(*N)
    return IntegrationsStatus(
        telegram=TelegramStatus(
            api_id=_field(v[N.TELEGRAM_API_ID], keep=2),
            api_hash=_field(v[N.TELEGRAM_API_HASH]),
            phone=_field(v[N.TELEGRAM_PHONE]),
            authorized=bool(v[N.TELEGRAM_SESSION]),
        ),
        kite=KiteStatus(
            api_key=_field(v[N.KITE_API_KEY]),
            api_secret=_field(v[N.KITE_API_SECRET], hint=False),
            session_active=bool(v[N.KITE_ACCESS_TOKEN]),
            user_id=v[N.KITE_USER_ID],
        ),
        llm=LLMStatus(api_key=_field(v[N.LLM_API_KEY])),
    )


async def _audit(container: ContainerDep, integration: str, action: str, fields: list[str]) -> None:
    await container.bus.publish(
        Event(
            type=EventType.INTEGRATION_UPDATED,
            aggregate_type="integration",
            payload={"integration": integration, "action": action, "fields": fields},
        )
    )


@router.put("/telegram", response_model=IntegrationsStatus)
async def put_telegram(body: TelegramCredentials, container: ContainerDep) -> IntegrationsStatus:
    mapping = {
        "api_id": N.TELEGRAM_API_ID,
        "api_hash": N.TELEGRAM_API_HASH,
        "phone": N.TELEGRAM_PHONE,
    }
    changed = [k for k, val in body.model_dump(exclude_none=True).items() if val]
    for k in changed:
        await container.secrets.put(mapping[k], getattr(body, k))
    if changed:
        # New credentials invalidate any existing Telegram login session.
        await container.secrets.delete(N.TELEGRAM_SESSION)
        await container.telegram.reload()
        await _audit(container, "telegram", "updated", changed)
    return await get_integrations(container)


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
async def delete_telegram(container: ContainerDep) -> None:
    await container.telegram.logout()
    await container.secrets.delete(
        N.TELEGRAM_API_ID, N.TELEGRAM_API_HASH, N.TELEGRAM_PHONE, N.TELEGRAM_SESSION
    )
    await container.telegram.reload()
    await _audit(container, "telegram", "cleared", [])


@router.put("/kite", response_model=IntegrationsStatus)
async def put_kite(body: KiteCredentials, container: ContainerDep) -> IntegrationsStatus:
    mapping = {"api_key": N.KITE_API_KEY, "api_secret": N.KITE_API_SECRET}
    changed = [k for k, val in body.model_dump(exclude_none=True).items() if val]
    for k in changed:
        await container.secrets.put(mapping[k], getattr(body, k))
    if changed:
        await container.secrets.delete(N.KITE_ACCESS_TOKEN, N.KITE_USER_ID)
        await _audit(container, "kite", "updated", changed)
    return await get_integrations(container)


@router.delete("/kite", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kite(container: ContainerDep) -> None:
    await container.secrets.delete(
        N.KITE_API_KEY, N.KITE_API_SECRET, N.KITE_ACCESS_TOKEN, N.KITE_USER_ID
    )
    await _audit(container, "kite", "cleared", [])


@router.put("/llm", response_model=IntegrationsStatus)
async def put_llm(body: LLMCredentials, container: ContainerDep) -> IntegrationsStatus:
    if body.api_key:
        await container.secrets.put(N.LLM_API_KEY, body.api_key)
        await _audit(container, "llm", "updated", ["api_key"])
    return await get_integrations(container)


@router.delete("/llm", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm(container: ContainerDep) -> None:
    await container.secrets.delete(N.LLM_API_KEY)
    await _audit(container, "llm", "cleared", [])
