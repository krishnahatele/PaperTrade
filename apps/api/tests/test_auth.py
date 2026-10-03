import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_PASSWORD

pytestmark = pytest.mark.db


async def test_setup_login_and_protection(anon_client: AsyncClient) -> None:
    c = anon_client
    st = (await c.get("/api/v1/auth/status")).json()
    assert st == {"auth_enabled": True, "configured": False, "authenticated": False}

    assert (await c.get("/api/v1/signals")).status_code == 401
    assert (await c.get("/health")).status_code == 200  # health stays public

    r = await c.post("/api/v1/auth/setup", json={"password": "short"})
    assert r.status_code == 400

    r = await c.post("/api/v1/auth/setup", json={"password": ADMIN_PASSWORD})
    assert r.status_code == 200
    token = r.json()["token"]

    r = await c.post("/api/v1/auth/setup", json={"password": ADMIN_PASSWORD})
    assert r.status_code == 409  # cannot re-run setup

    h = {"Authorization": f"Bearer {token}"}
    assert (await c.get("/api/v1/signals", headers=h)).status_code == 200
    st = (await c.get("/api/v1/auth/status", headers=h)).json()
    assert st["authenticated"] is True

    assert (await c.post("/api/v1/auth/login", json={"password": "nope"})).status_code == 401
    r = await c.post("/api/v1/auth/login", json={"password": ADMIN_PASSWORD})
    assert r.status_code == 200


async def test_change_password_revokes_tokens(db_client: AsyncClient) -> None:
    old = db_client.headers["Authorization"]
    r = await db_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "a brand new password"},
    )
    assert r.status_code == 200
    assert (
        await db_client.get("/api/v1/signals", headers={"Authorization": old})
    ).status_code == 401
    new = {"Authorization": f"Bearer {r.json()['token']}"}
    assert (await db_client.get("/api/v1/signals", headers=new)).status_code == 200


async def test_login_rate_limited(anon_client: AsyncClient) -> None:
    await anon_client.post("/api/v1/auth/setup", json={"password": ADMIN_PASSWORD})
    codes = [
        (await anon_client.post("/api/v1/auth/login", json={"password": "bad"})).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
