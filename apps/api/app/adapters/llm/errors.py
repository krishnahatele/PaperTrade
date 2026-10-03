from __future__ import annotations

from app.core.errors import MarketOSError


class LLMError(MarketOSError):
    status_code = 502
    code = "llm_error"
