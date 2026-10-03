import json
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.adapters.llm import LLMMessage, LLMRequest
from app.adapters.llm.anthropic_adapter import supports_effort, supports_fallbacks
from app.adapters.llm.errors import LLMError
from app.adapters.llm.openai_compat import OpenAICompatibleAdapter, extract_json
from app.container import Container
from tests.fakes import FakeLLM

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


def test_anthropic_model_capabilities() -> None:
    assert supports_effort("claude-opus-5-5")
    assert not supports_effort("claude-haiku-4-5")  # Haiku rejects `effort`
    assert supports_fallbacks("claude-opus-5-5")
    assert not supports_fallbacks("claude-haiku-4-5")


def test_extract_json() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(json.JSONDecodeError):
        extract_json("no json here")


def _adapter(handler: Any) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        "https://llm.example/v1",
        "key-123",
        "mini",
        name="gemini",
        transport=httpx.MockTransport(handler),
    )


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "mini",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        },
    )


async def test_openai_compat_json_schema() -> None:
    seen: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer key-123"
        assert req.url.path == "/v1/chat/completions"
        seen.append(json.loads(req.content))
        return _ok('{"ok": true}')

    out = await _adapter(handler).complete(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")], response_schema=SCHEMA)
    )
    assert out.parsed == {"ok": True}
    assert out.input_tokens == 3
    assert seen[0]["response_format"]["type"] == "json_schema"
    assert seen[0]["model"] == "mini"


async def test_openai_compat_falls_back_to_json_mode() -> None:
    formats: list[str | None] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        fmt = (body.get("response_format") or {}).get("type")
        formats.append(fmt)
        if fmt == "json_schema":
            return httpx.Response(400, json={"error": "unsupported"})
        return _ok('```json\n{"ok": false}\n```')

    out = await _adapter(handler).complete(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")], response_schema=SCHEMA)
    )
    assert formats == ["json_schema", "json_object"]
    assert out.parsed == {"ok": False}


async def test_openai_compat_errors_and_models() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "models/flash"}, {"id": "embed-1"}]})
        return httpx.Response(401, json={"error": "bad key"})

    a = _adapter(handler)
    with pytest.raises(LLMError, match="rejected the API key"):
        await a.complete(LLMRequest(messages=[LLMMessage(role="user", content="x")]))
    assert await a.list_models() == ["embed-1", "flash"]


@pytest.mark.db
async def test_provider_switch_keys_and_model_list(db_client: AsyncClient) -> None:
    c = db_client
    container: Container = c._transport.app.state.container  # type: ignore[attr-defined]
    built: list[tuple[Any, ...]] = []

    class Lister(FakeLLM):
        async def list_models(self) -> list[str]:
            return ["gemini-flash", "text-embedding-004"]

    def factory(provider: Any, base_url: Any, key: Any, model: str) -> FakeLLM:
        built.append((provider.value, base_url, key, model))
        return Lister({"is_signal": False, "confidence": 0})

    container.llm.factory = factory

    provs = {p["id"]: p for p in (await c.get("/api/v1/llm/providers")).json()}
    assert provs["anthropic"]["active"] is True
    assert provs["gemini"]["key_set"] is False

    # Keys are stored per provider.
    await c.put("/api/v1/integrations/llm", json={"provider": "gemini", "api_key": "AIza-test-key"})
    await c.put(
        "/api/v1/integrations/llm", json={"provider": "anthropic", "api_key": "sk-ant-test-1"}
    )
    provs = {p["id"]: p for p in (await c.get("/api/v1/llm/providers")).json()}
    assert provs["gemini"]["key_set"] is True
    assert provs["groq"]["key_set"] is False

    r = await c.get("/api/v1/llm/models", params={"provider": "gemini"})
    assert r.json()["models"] == ["gemini-flash"]  # embeddings filtered out

    r = await c.patch(
        "/api/v1/settings/parsing", json={"llm_provider": "gemini", "llm_model": "gemini-flash"}
    )
    assert r.status_code == 200
    assert built[-1] == (
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "AIza-test-key",
        "gemini-flash",
    )
    integ = (await c.get("/api/v1/integrations")).json()["llm"]
    assert integ["provider"] == "gemini"
    assert integ["api_key"]["set"] is True

    r = await c.patch("/api/v1/settings/parsing", json={"llm_provider": "nope"})
    assert r.status_code == 422

    # Provider without a key -> AI disabled with a clear reason.
    await c.patch("/api/v1/settings/parsing", json={"llm_provider": "groq"})
    info = (await c.get("/api/v1/system/info")).json()["adapters"]["llm"]
    assert info["state"] == "not_configured"
    assert "Groq" in info["detail"]

    # Custom endpoint uses the configured base URL, no key required.
    await c.patch(
        "/api/v1/settings/parsing",
        json={
            "llm_provider": "custom",
            "llm_base_url": "http://my-llm:8000/v1",
            "llm_model": "local",
        },
    )
    last: tuple[Any, ...] = tuple(built[-1])
    assert last == ("custom", "http://my-llm:8000/v1", None, "local")

    r = await c.post("/api/v1/llm/test", json={"text": "hello"})
    assert r.status_code == 200
    assert r.json()["is_signal"] is False


@pytest.mark.parametrize(("code", "text"), [(404, "not found"), (410, "retired")])
async def test_openai_compat_model_errors_are_clear(code: int, text: str) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text="404 page not found")

    with pytest.raises(LLMError, match=text):
        await _adapter(handler).complete(
            LLMRequest(messages=[LLMMessage(role="user", content="x")])
        )


@pytest.mark.db
async def test_nvidia_preset(db_client: AsyncClient) -> None:
    provs = {p["id"]: p for p in (await db_client.get("/api/v1/llm/providers")).json()}
    assert provs["nvidia"]["base_url"] == "https://integrate.api.nvidia.com/v1"
