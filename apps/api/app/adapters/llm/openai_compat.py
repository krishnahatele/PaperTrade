"""LLMAdapter for any OpenAI-compatible Chat Completions endpoint
(OpenAI, Gemini, Groq, DeepSeek, OpenRouter, Ollama, vLLM, ...)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse
from app.adapters.llm.errors import LLMError


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating ```json fences and surrounding prose."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start : end + 1])
        raise


class OpenAICompatibleAdapter(LLMAdapter):
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        name: str = "openai-compatible",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=60.0, transport=transport
        )

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.READY, detail=f"Model {self.model}")

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        try:
            return await self._client.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach {self.base_url}: {type(exc).__name__}") from exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": 0,
        }
        schema = request.response_schema
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            }
        resp = await self._post(body)
        if schema is not None and resp.status_code in (400, 422):
            # Provider lacks json_schema support: fall back to JSON mode + schema in the prompt.
            hint = "Reply with only a JSON object matching this JSON Schema:\n" + json.dumps(schema)
            body["messages"] = [{"role": "system", "content": hint}, *messages]
            body["response_format"] = {"type": "json_object"}
            resp = await self._post(body)
            if resp.status_code in (400, 422):
                body.pop("response_format")
                resp = await self._post(body)
        if resp.status_code in (401, 403):
            raise LLMError(f"{self.name} rejected the API key.")
        if resp.status_code == 429:
            raise LLMError(f"{self.name} rate limit reached; try again shortly.")
        if resp.status_code == 404:
            raise LLMError(
                f"Model '{self.model}' was not found on {self.name}. Pick another model."
            )
        if resp.status_code == 410:
            raise LLMError(
                f"Model '{self.model}' has been retired by {self.name}. Pick another model."
            )
        if resp.status_code >= 400:
            raise LLMError(f"{self.name} error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name} returned an unexpected response.") from exc
        parsed = None
        if schema is not None:
            try:
                parsed = extract_json(text)
            except json.JSONDecodeError as exc:
                raise LLMError("Model returned invalid JSON.") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            content=text,
            model=data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            parsed=parsed,
        )

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get("/models")
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach {self.base_url}: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise LLMError(f"Could not list models ({r.status_code}).")
        items = r.json().get("data") or r.json().get("models") or []
        ids = [str(m.get("id") or m.get("name") or "") for m in items]
        return sorted({i.removeprefix("models/") for i in ids if i})

    async def close(self) -> None:
        await self._client.aclose()
