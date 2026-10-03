"""Unit tests for the Anthropic adapter with the SDK call stubbed out."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.llm import LLMMessage, LLMRequest
from app.adapters.llm.anthropic_adapter import AnthropicLLMAdapter, LLMError


def _resp(text: str, stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="text", text=text)],
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


@pytest.fixture
def adapter() -> AnthropicLLMAdapter:
    return AnthropicLLMAdapter("sk-ant-test", "claude-opus-5-5")


def _stub(adapter: AnthropicLLMAdapter, resp: Any, calls: list[dict[str, Any]]) -> None:
    async def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return resp

    adapter._client.beta.messages.create = create  # type: ignore[method-assign]


async def test_request_shape_and_json(adapter: AnthropicLLMAdapter) -> None:
    calls: list[dict[str, Any]] = []
    _stub(adapter, _resp('{"ok": true}'), calls)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    out = await adapter.complete(
        LLMRequest(
            messages=[
                LLMMessage(role="system", content="sys"),
                LLMMessage(role="user", content="hi"),
            ],
            response_schema=schema,
        )
    )
    assert out.parsed == {"ok": True}
    kw = calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["system"] == "sys"
    assert kw["messages"] == [{"role": "user", "content": "hi"}]
    assert kw["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": schema},
    }
    assert kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in kw
    assert "temperature" not in kw


async def test_refusal_raises(adapter: AnthropicLLMAdapter) -> None:
    _stub(adapter, _resp("", stop="refusal"), [])
    with pytest.raises(LLMError, match="declined"):
        await adapter.complete(LLMRequest(messages=[LLMMessage(role="user", content="x")]))


async def test_invalid_json_raises(adapter: AnthropicLLMAdapter) -> None:
    _stub(adapter, _resp("not json"), [])
    with pytest.raises(LLMError, match="invalid JSON"):
        await adapter.complete(
            LLMRequest(
                messages=[LLMMessage(role="user", content="x")], response_schema={"type": "object"}
            )
        )
