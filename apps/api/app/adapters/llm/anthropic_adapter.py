"""LLMAdapter backed by the Anthropic Messages API."""

from __future__ import annotations

import json
from typing import Literal

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse
from app.core.errors import MarketOSError

# Server-side refusal fallback: if the model declines, the API re-runs the request
# on Anthropic's recommended fallback model inside the same call.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(MarketOSError):
    status_code = 502
    code = "llm_error"


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
        output_config: BetaOutputConfigParam = {"effort": self.effort}
        if request.response_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.response_schema}
        try:
            resp = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=system or anthropic.omit,
                messages=messages,
                output_config=output_config,
                betas=[_FALLBACK_BETA],
                fallbacks="default",
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
