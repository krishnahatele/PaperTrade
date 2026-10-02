"""Single-user authentication: one admin password, signed bearer tokens."""

from __future__ import annotations

import time
from collections import deque

from app.core.crypto import PasswordHash, SecretBox
from app.core.errors import ConflictError, MarketOSError
from app.services.runtime import AuthRuntime, RuntimeStore
from app.services.secrets import SecretName, SecretStore

MIN_PASSWORD_LENGTH = 10


class AuthError(MarketOSError):
    status_code = 401
    code = "unauthorized"


class RateLimitedError(MarketOSError):
    status_code = 429
    code = "rate_limited"


class LoginRateLimiter:
    """At most ``max_attempts`` failed logins per ``window`` seconds (process-wide)."""

    def __init__(self, max_attempts: int = 5, window: float = 60.0) -> None:
        self.max_attempts = max_attempts
        self.window = window
        self._failures: deque[float] = deque()

    def check(self) -> None:
        now = time.monotonic()
        while self._failures and now - self._failures[0] > self.window:
            self._failures.popleft()
        if len(self._failures) >= self.max_attempts:
            raise RateLimitedError("Too many failed login attempts. Try again in a minute.")

    def record_failure(self) -> None:
        self._failures.append(time.monotonic())


class AuthService:
    def __init__(
        self,
        secrets: SecretStore,
        runtime: RuntimeStore,
        box: SecretBox,
        ttl_hours: int,
        limiter: LoginRateLimiter,
    ) -> None:
        self.secrets = secrets
        self.runtime = runtime
        self.box = box
        self.ttl_seconds = ttl_hours * 3600
        self.limiter = limiter

    async def is_configured(self) -> bool:
        return await self.secrets.get(SecretName.AUTH_PASSWORD_HASH) is not None

    async def setup(self, password: str) -> tuple[str, int]:
        if await self.is_configured():
            raise ConflictError("Admin password is already set.")
        await self._store_password(password)
        return await self._issue()

    async def login(self, password: str) -> tuple[str, int]:
        self.limiter.check()
        stored = await self.secrets.get(SecretName.AUTH_PASSWORD_HASH)
        if stored is None:
            raise AuthError("No admin password set yet. Complete setup first.")
        if not PasswordHash(stored).verify(password):
            self.limiter.record_failure()
            raise AuthError("Incorrect password.")
        return await self._issue()

    async def change_password(self, current: str, new: str) -> tuple[str, int]:
        await self.login(current)
        await self._store_password(new)
        # Bump generation: every previously issued token becomes invalid.
        rt = await self.runtime.get(AuthRuntime)
        await self.runtime.update(AuthRuntime, token_generation=rt.token_generation + 1)
        return await self._issue()

    async def verify(self, token: str) -> bool:
        rt = await self.runtime.get(AuthRuntime)
        return self.box.verify_token(token, rt.token_generation)

    async def _issue(self) -> tuple[str, int]:
        rt = await self.runtime.get(AuthRuntime)
        return self.box.issue_token(self.ttl_seconds, rt.token_generation)

    async def _store_password(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise MarketOSError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        await self.secrets.put(SecretName.AUTH_PASSWORD_HASH, PasswordHash.create(password).value)
