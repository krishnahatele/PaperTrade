"""Encrypted credential storage backed by the ``secrets`` table."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import SecretBox
from app.models import SecretRecord


class SecretName(StrEnum):
    AUTH_PASSWORD_HASH = "auth.password_hash"  # noqa: S105 - name, not a secret
    TELEGRAM_API_ID = "telegram.api_id"
    TELEGRAM_API_HASH = "telegram.api_hash"
    TELEGRAM_PHONE = "telegram.phone"
    TELEGRAM_SESSION = "telegram.session"
    TELEGRAM_BOT_TOKEN = "telegram.bot_token"  # noqa: S105 - name, not a secret
    KITE_API_KEY = "kite.api_key"
    KITE_API_SECRET = "kite.api_secret"  # noqa: S105
    KITE_ACCESS_TOKEN = "kite.access_token"  # noqa: S105
    KITE_USER_ID = "kite.user_id"
    LLM_API_KEY = "llm.api_key"  # legacy (Anthropic) key from before multi-provider


def llm_key_name(provider: str) -> str:
    return f"llm.api_key.{provider}"


class SecretStore:
    """Encrypts on write, decrypts on read. Values never leave via the API."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], box: SecretBox) -> None:
        self._sf = session_factory
        self._box = box

    async def get(self, name: str) -> str | None:
        async with self._sf() as s:
            rec = await s.get(SecretRecord, str(name))
            return None if rec is None else self._box.decrypt(rec.ciphertext)

    async def get_many(self, *names: SecretName) -> dict[SecretName, str | None]:
        async with self._sf() as s:
            rows = await s.scalars(
                select(SecretRecord).where(SecretRecord.name.in_([n.value for n in names]))
            )
            found = {r.name: self._box.decrypt(r.ciphertext) for r in rows}
        return {n: found.get(n.value) for n in names}

    async def put(self, name: str, value: str) -> None:
        async with self._sf() as s:
            rec = await s.get(SecretRecord, str(name))
            ct = self._box.encrypt(value)
            if rec is None:
                s.add(SecretRecord(name=str(name), ciphertext=ct))
            else:
                rec.ciphertext = ct
            await s.commit()

    async def delete(self, *names: str) -> None:
        async with self._sf() as s:
            await s.execute(
                delete(SecretRecord).where(SecretRecord.name.in_([str(n) for n in names]))
            )
            await s.commit()

    async def present(self) -> set[str]:
        async with self._sf() as s:
            return set(await s.scalars(select(SecretRecord.name)))
