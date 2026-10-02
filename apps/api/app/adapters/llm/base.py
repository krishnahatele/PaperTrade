"""LLMAdapter: provider-neutral text completion with optional structured output.

Used in a later phase to turn raw messages into structured signals. Callers
must treat LLM output as untrusted and validate it against a schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.adapters.base import AdapterHealth


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    messages: list[LLMMessage]
    max_tokens: int = Field(default=1024, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    # Optional JSON Schema the response must conform to.
    response_schema: dict[str, Any] | None = None


class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    parsed: dict[str, Any] | None = None


class LLMAdapter(ABC):
    name: str

    @abstractmethod
    async def health(self) -> AdapterHealth: ...

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
