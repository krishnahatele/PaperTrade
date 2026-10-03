"""LLMAdapter backed by the Anthropic Messages API."""

from __future__ import annotations

import json
from typing import Literal

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse
from app.adapters.llm.errors import LLMError

# Server-side refusal fallback: if the model declines, the API re-runs the request
# on Anthropic's recommended fallback model inside the same call. Only the newest
# models accept it.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")
# Models that reject the `effort` parameter.
_NO_EFFORT_PREFIXES = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-3")


def supports_fallbacks(model: str) -> bool:
    return model in _FALLBACK_MODELS


def supports_effort(model: str) -> bool:
    return not model.startswith(_NO_EFFORT_PREFIXES)


__all__ = ["AnthropicLLMAdapter", "LLMError"]


class AnthropicLLMAdapter(LLMAdapter):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        effort: Literal["low", "medium", "high", "xhigh", "max"] = "low",
    ) -> None:
        self.model = model
        self.effort = effort
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0, max_retries=2)

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.READY, detail=f"Model {self.model}")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        messages: list[BetaMessageParam] = [
            {"role": m.role, "content": m.content} for m in request.messages if m.role != "system"
        ]
        output_config: BetaOutputConfigParam = {}
        if supports_effort(self.model):
            output_config["effort"] = self.effort
        if request.response_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.response_schema}
        fallback = supports_fallbacks(self.model)
        try:
            resp = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=system or anthropic.omit,
                messages=messages,
                output_config=output_config or anthropic.omit,
                betas=[_FALLBACK_BETA] if fallback else anthropic.omit,
                fallbacks="default" if fallback else anthropic.omit,
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached; try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Cannot reach the Anthropic API.") from exc

        if resp.stop_reason == "refusal":
            raise LLMError("The model declined to process this message.")
        text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text")
        parsed = None
        if request.response_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMError("Model returned invalid JSON.") from exc
        return LLMResponse(
            content=text,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            parsed=parsed,
        )

    async def list_models(self) -> list[str]:
        try:
            page = await self._client.models.list(limit=100)
        except anthropic.APIError as exc:
            raise LLMError(f"Could not list Anthropic models: {exc}") from exc
        return [m.id for m in page.data]

    async def close(self) -> None:
        await self._client.close()
