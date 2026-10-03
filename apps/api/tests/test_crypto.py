import time
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import DecryptionError, PasswordHash, SecretBox, load_master_key
from tests.conftest import make_settings


def test_encrypt_roundtrip_and_wrong_key() -> None:
    box = SecretBox(Fernet.generate_key())
    ct = box.encrypt("api-hash-123")
    assert b"api-hash-123" not in ct
    assert box.decrypt(ct) == "api-hash-123"
    with pytest.raises(DecryptionError):
        SecretBox(Fernet.generate_key()).decrypt(ct)


def test_master_key_file_is_generated_once(tmp_path: Path) -> None:
    keyfile = tmp_path / "sub" / "master.key"
    s = make_settings(secret_key=None, secret_key_file=str(keyfile))
    k1 = load_master_key(s)
    assert keyfile.stat().st_mode & 0o777 == 0o600
    assert load_master_key(s) == k1


def test_password_hash() -> None:
    h = PasswordHash.create("hunter2hunter2")
    assert h.value.startswith("scrypt$")
    assert h.verify("hunter2hunter2")
    assert not h.verify("wrong")
    assert not PasswordHash("garbage").verify("x")


def test_tokens() -> None:
    box = SecretBox(Fernet.generate_key())
    token, exp = box.issue_token(60, generation=3)
    assert exp > time.time()
    assert box.verify_token(token, 3)
    assert not box.verify_token(token, 4)  # revoked by generation bump
    assert not box.verify_token(token + "x", 3)
    assert not box.verify_token("nonsense", 3)
    expired, _ = box.issue_token(-1, generation=3)
    assert not box.verify_token(expired, 3)
    assert not SecretBox(Fernet.generate_key()).verify_token(token, 3)
