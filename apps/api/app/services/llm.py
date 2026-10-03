"""Builds the LLM adapter for the selected provider from encrypted keys and settings."""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.llm import DisabledLLMAdapter, LLMAdapter
from app.adapters.llm.errors import LLMError
from app.adapters.llm.providers import PRESETS, LLMProvider, is_chat_model
from app.services.runtime import ParsingRuntime, RuntimeStore
from app.services.secrets import SecretName, SecretStore, llm_key_name

# (provider, base_url, api_key, model) -> adapter
LLMFactory = Callable[[LLMProvider, str | None, str | None, str], LLMAdapter]


def build_adapter(
    provider: LLMProvider, base_url: str | None, api_key: str | None, model: str
) -> LLMAdapter:
    if provider is LLMProvider.ANTHROPIC:
        from app.adapters.llm.anthropic_adapter import AnthropicLLMAdapter

        if not api_key:
            raise LLMError("Anthropic needs an API key.")
        return AnthropicLLMAdapter(api_key, model)
    from app.adapters.llm.openai_compat import OpenAICompatibleAdapter

    if not base_url:
        raise LLMError("Set the base URL for this provider.")
    return OpenAICompatibleAdapter(base_url, api_key, model, name=provider.value)


class LLMService:
    def __init__(
        self, secrets: SecretStore, runtime: RuntimeStore, factory: LLMFactory = build_adapter
    ) -> None:
        self.secrets = secrets
        self.runtime = runtime
        self.factory = factory
        self.adapter: LLMAdapter = DisabledLLMAdapter()
        self.configured = False
        self.provider: LLMProvider | None = None
        self.model: str | None = None
        self.error: str | None = None

    async def api_key(self, provider: LLMProvider) -> str | None:
        key = await self.secrets.get(llm_key_name(provider))
        if key is None and provider is LLMProvider.ANTHROPIC:
            key = await self.secrets.get(SecretName.LLM_API_KEY)  # legacy single key
        return key

    @staticmethod
    def base_url(parsing: ParsingRuntime, provider: LLMProvider) -> str | None:
        preset = PRESETS[provider]
        if provider in (LLMProvider.CUSTOM, LLMProvider.OLLAMA) and parsing.llm_base_url:
            return parsing.llm_base_url
        return preset.base_url

    async def build(self, provider: LLMProvider, model: str | None = None) -> LLMAdapter:
        parsing = await self.runtime.get(ParsingRuntime)
        key = await self.api_key(provider)
        if PRESETS[provider].needs_key and not key:
            raise LLMError(f"Add an API key for {PRESETS[provider].label} first.")
        return self.factory(
            provider, self.base_url(parsing, provider), key, model or parsing.llm_model
        )

    async def reload(self) -> None:
        old = self.adapter
        parsing = await self.runtime.get(ParsingRuntime)
        self.provider, self.model = parsing.llm_provider, parsing.llm_model
        try:
            self.adapter = await self.build(parsing.llm_provider)
            self.configured, self.error = True, None
        except LLMError as exc:
            self.adapter, self.configured, self.error = DisabledLLMAdapter(), False, exc.message
        close = getattr(old, "close", None)
        if close is not None and old is not self.adapter:
            with contextlib.suppress(Exception):  # best-effort cleanup
                await close()

    async def list_models(self, provider: LLMProvider) -> list[str]:
        adapter = await self.build(provider, model="-")
        lister = getattr(adapter, "list_models", None)
        if lister is None:
            return []
        try:
            models: list[str] = await lister()
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                await close()
        return [m for m in models if is_chat_model(m)]

    async def health(self) -> AdapterHealth:
        if not self.configured:
            return AdapterHealth(
                name="disabled",
                state=AdapterState.NOT_CONFIGURED,
                detail=self.error or "Choose an AI provider and add its key in Settings.",
            )
        label = PRESETS[self.provider].label if self.provider else "AI"
        return AdapterHealth(
            name=self.adapter.name, state=AdapterState.READY, detail=f"{label} · {self.model}"
        )
