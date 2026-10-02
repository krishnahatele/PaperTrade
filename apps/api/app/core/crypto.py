"""Symmetric encryption for credentials at rest, plus password hashing and tokens.

* Credentials (Telegram/Kite/LLM keys, Telegram session) are encrypted with
  Fernet (AES-128-CBC + HMAC-SHA256) using a master key that never touches the
  database.
* The admin password is hashed with scrypt (stdlib).
* Session tokens are HMAC-SHA256 signed with a key derived from the master key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("marketos.crypto")


class DecryptionError(Exception):
    """Stored ciphertext could not be decrypted (wrong or rotated master key)."""


def load_master_key(settings: Settings) -> bytes:
    if settings.secret_key is not None:
        key = settings.secret_key.get_secret_value().encode()
        Fernet(key)  # validates format
        return key

    path = Path(settings.secret_key_file)
    if path.exists():
        return path.read_bytes().strip()

    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    log.warning("crypto.master_key_generated", path=str(path.resolve()))
    return key


class SecretBox:
    def __init__(self, master_key: bytes) -> None:
        self._fernet = Fernet(master_key)
        self._signing_key = hmac.new(master_key, b"marketos/token-signing/v1", "sha256").digest()

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as exc:
            raise DecryptionError("cannot decrypt secret; was the master key changed?") from exc

    # --- Tokens -----------------------------------------------------------
    def issue_token(self, ttl_seconds: int, generation: int) -> tuple[str, int]:
        exp = int(time.time()) + ttl_seconds
        nonce = secrets.token_urlsafe(12)
        body = f"v1.{generation}.{exp}.{nonce}"
        return f"{body}.{self._sign(body)}", exp

    def verify_token(self, token: str, generation: int) -> bool:
        try:
            version, gen, exp, nonce, sig = token.split(".")
        except ValueError:
            return False
        body = f"{version}.{gen}.{exp}.{nonce}"
        if not hmac.compare_digest(sig, self._sign(body)):
            return False
        return version == "v1" and gen == str(generation) and int(exp) > time.time()

    def _sign(self, body: str) -> str:
        mac = hmac.new(self._signing_key, body.encode(), "sha256").digest()
        return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


# --- Password hashing (scrypt) -----------------------------------------------
_N, _R, _P = 2**14, 8, 1


@dataclass(frozen=True)
class PasswordHash:
    value: str

    @classmethod
    def create(cls, password: str) -> PasswordHash:
        salt = secrets.token_bytes(16)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
        enc = base64.b64encode
        return cls(f"scrypt${_N}${_R}${_P}${enc(salt).decode()}${enc(dk).decode()}")

    def verify(self, password: str) -> bool:
        try:
            _, n, r, p, salt_b64, dk_b64 = self.value.split("$")
            salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
            dk = hashlib.scrypt(
                password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(dk, expected)
