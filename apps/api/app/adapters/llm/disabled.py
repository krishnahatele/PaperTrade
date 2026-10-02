from __future__ import annotations

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.llm.base import LLMAdapter, LLMRequest, LLMResponse
from app.core.errors import FeatureDisabledError

_MSG = "LLM features are not available in Phase 0."


class DisabledLLMAdapter(LLMAdapter):
    name = "disabled"

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.DISABLED, detail=_MSG)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise FeatureDisabledError(_MSG)
