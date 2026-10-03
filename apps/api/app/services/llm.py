"""Builds the LLM adapter from the encrypted API key and parsing settings."""

from __future__ import annotations

from collections.abc import Callable

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.llm import DisabledLLMAdapter, LLMAdapter
from app.services.runtime import ParsingRuntime, RuntimeStore
from app.services.secrets import SecretName, SecretStore

LLMFactory = Callable[[str, str], LLMAdapter]


def build_anthropic(api_key: str, model: str) -> LLMAdapter:
    from app.adapters.llm.anthropic_adapter import AnthropicLLMAdapter

    return AnthropicLLMAdapter(api_key, model)


class LLMService:
    def __init__(
        self, secrets: SecretStore, runtime: RuntimeStore, factory: LLMFactory = build_anthropic
    ) -> None:
        self.secrets = secrets
        self.runtime = runtime
        self.factory = factory
        self.adapter: LLMAdapter = DisabledLLMAdapter()
        self.configured = False

    async def reload(self) -> None:
        key = await self.secrets.get(SecretName.LLM_API_KEY)
        parsing = await self.runtime.get(ParsingRuntime)
        if key and parsing.llm_provider == "anthropic":
            self.adapter = self.factory(key, parsing.llm_model)
            self.configured = True
        else:
            self.adapter = DisabledLLMAdapter()
            self.configured = False

    async def health(self) -> AdapterHealth:
        if not self.configured:
            return AdapterHealth(
                name="disabled",
                state=AdapterState.NOT_CONFIGURED,
                detail="Add an Anthropic API key in Settings to enable AI parsing.",
            )
        return await self.adapter.health()
