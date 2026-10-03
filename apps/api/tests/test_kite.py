from typing import Any

import pytest
from httpx import AsyncClient

from app.core.errors import InvalidInputError
from app.services.kite import extract_request_token


def test_extract_request_token() -> None:
    assert extract_request_token("abcDEF12345") == "abcDEF12345"
    url = "https://127.0.0.1/?action=login&type=login&status=success&request_token=Tok3n123456"
    assert extract_request_token(url) == "Tok3n123456"
    with pytest.raises(InvalidInputError):
        extract_request_token("https://example.com/?status=fail")
    with pytest.raises(InvalidInputError):
        extract_request_token("bad token!")


@pytest.mark.db
async def test_kite_login_flow(db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    c = db_client
    assert (await c.get("/api/v1/kite/login-url")).status_code == 403
    await c.put(
        "/api/v1/integrations/kite", json={"api_key": "kitekey1", "api_secret": "kitesecret"}
    )
    url = (await c.get("/api/v1/kite/login-url")).json()["url"]
    assert "api_key=kitekey1" in url

    from kiteconnect import KiteConnect

    def fake_generate(self: Any, request_token: str, api_secret: str) -> dict[str, str]:
        assert (request_token, api_secret) == ("Tok3n123456", "kitesecret")
        return {"access_token": "acc-tok", "user_id": "AB1234"}

    monkeypatch.setattr(KiteConnect, "generate_session", fake_generate)
    r = await c.post(
        "/api/v1/kite/session", json={"request_token": "https://x/?request_token=Tok3n123456"}
    )
    assert r.json() == {"configured": True, "session_active": True, "user_id": "AB1234"}
    info = (await c.get("/api/v1/system/info")).json()["adapters"]["market_data"]
    assert info["name"] == "kite"
    assert (await c.get("/api/v1/integrations")).json()["kite"]["session_active"] is True
    assert "acc-tok" not in (await c.get("/api/v1/integrations")).text

    assert (await c.post("/api/v1/kite/logout")).status_code == 204
    assert (await c.get("/api/v1/kite/status")).json()["session_active"] is False
