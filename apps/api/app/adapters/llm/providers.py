"""Supported LLM providers. Every non-Anthropic provider is reached through the
OpenAI-compatible Chat Completions API, so adding one is just a preset."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    NVIDIA = "nvidia"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class ProviderPreset(BaseModel):
    id: LLMProvider
    label: str
    base_url: str | None
    needs_key: bool
    key_hint: str
    note: str
    suggested_models: list[str]


PRESETS: dict[LLMProvider, ProviderPreset] = {
    p.id: p
    for p in [
        ProviderPreset(
            id=LLMProvider.ANTHROPIC,
            label="Anthropic (Claude)",
            base_url=None,
            needs_key=True,
            key_hint="sk-ant-…  (console.anthropic.com)",
            note="Highest accuracy. Claude Haiku 4.5 is the low-cost option.",
            suggested_models=["claude-haiku-4-5", "claude-sonnet-5-5", "claude-opus-5-5"],
        ),
        ProviderPreset(
            id=LLMProvider.GEMINI,
            label="Google Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            needs_key=True,
            key_hint="AIza…  (aistudio.google.com)",
            note="Has a free tier; Flash models are very cheap.",
            suggested_models=[],
        ),
        ProviderPreset(
            id=LLMProvider.GROQ,
            label="Groq",
            base_url="https://api.groq.com/openai/v1",
            needs_key=True,
            key_hint="gsk_…  (console.groq.com)",
            note="Free tier, very fast open models.",
            suggested_models=[],
        ),
        ProviderPreset(
            id=LLMProvider.DEEPSEEK,
            label="DeepSeek",
            base_url="https://api.deepseek.com/v1",
            needs_key=True,
            key_hint="sk-…  (platform.deepseek.com)",
            note="Very low cost per message.",
            suggested_models=["deepseek-chat"],
        ),
        ProviderPreset(
            id=LLMProvider.OPENAI,
            label="OpenAI",
            base_url="https://api.openai.com/v1",
            needs_key=True,
            key_hint="sk-…  (platform.openai.com)",
            note="Use a 'mini' model for low cost.",
            suggested_models=[],
        ),
        ProviderPreset(
            id=LLMProvider.NVIDIA,
            label="NVIDIA (build.nvidia.com)",
            base_url="https://integrate.api.nvidia.com/v1",
            needs_key=True,
            key_hint="nvapi-…  (build.nvidia.com → API Keys)",
            note="Free developer credits. Pick an '-instruct' model; some are retired.",
            suggested_models=[],
        ),
        ProviderPreset(
            id=LLMProvider.OPENROUTER,
            label="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            needs_key=True,
            key_hint="sk-or-…  (openrouter.ai)",
            note="One key for hundreds of models, including free ones.",
            suggested_models=[],
        ),
        ProviderPreset(
            id=LLMProvider.OLLAMA,
            label="Ollama (self-hosted)",
            base_url="http://localhost:11434/v1",
            needs_key=False,
            key_hint="not needed",
            note="Free; runs models on your own machine (needs a capable computer).",
            suggested_models=[],
        ),
        ProviderPreset(
            id=LLMProvider.CUSTOM,
            label="Custom (OpenAI-compatible)",
            base_url=None,
            needs_key=False,
            key_hint="if your endpoint needs one",
            note="Any server implementing /chat/completions (vLLM, LM Studio, Together, …).",
            suggested_models=[],
        ),
    ]
}

_NON_CHAT = (
    "embed",
    "tts",
    "whisper",
    "dall-e",
    "image",
    "audio",
    "moderation",
    "transcribe",
    "realtime",
    "search",
    "guard",
    "rerank",
    "aqa",
    "imagen",
    "veo",
    "learnlm",
)


def is_chat_model(model_id: str) -> bool:
    m = model_id.lower()
    return not any(k in m for k in _NON_CHAT)
