from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.adapters.llm.providers import PRESETS, LLMProvider, ProviderPreset
from app.api.deps import ContainerDep
from app.parsing.llm import parse_llm
from app.schemas.signal import ParsePreview
from app.services.runtime import ParsingRuntime

router = APIRouter(prefix="/llm", tags=["ai"])

SAMPLE = "Bank nifty 52000 put looks good, take it near 300, exit if 250 breaks, aim 350 then 400"


class ProviderInfo(ProviderPreset):
    key_set: bool
    active: bool


class ModelList(BaseModel):
    provider: LLMProvider
    models: list[str]


class TestBody(BaseModel):
    text: str = Field(default=SAMPLE, min_length=1, max_length=4000)


@router.get("/providers", response_model=list[ProviderInfo])
async def providers(container: ContainerDep) -> list[ProviderInfo]:
    parsing = await container.runtime.get(ParsingRuntime)
    out = []
    for p in PRESETS.values():
        key = await container.llm.api_key(p.id)
        out.append(
            ProviderInfo(**p.model_dump(), key_set=bool(key), active=p.id is parsing.llm_provider)
        )
    return out


@router.get("/models", response_model=ModelList, summary="Live model list from the provider")
async def models(container: ContainerDep, provider: LLMProvider = Query(...)) -> ModelList:
    return ModelList(provider=provider, models=await container.llm.list_models(provider))


@router.post(
    "/test",
    response_model=ParsePreview,
    summary="Parse a sample message with the configured AI model (one paid call)",
)
async def run_llm_test(container: ContainerDep, body: TestBody | None = None) -> ParsePreview:
    text = (body or TestBody()).text
    await container.llm.reload()
    p = await parse_llm(container.llm.adapter, text)
    return ParsePreview(
        parser=None,
        is_signal=p.is_signal,
        reason=p.reason,
        side=p.side.value if p.side else None,
        symbol_text=p.symbol_text,
        underlying=p.underlying,
        instrument_type=p.instrument_type.value if p.instrument_type else None,
        strike=p.strike,
        expiry_text=p.expiry_text,
        entry_low=p.entry_low,
        entry_high=p.entry_high,
        stop_loss=p.stop_loss,
        targets=p.targets,
        confidence=p.confidence,
        warnings=p.warnings,
        llm_error=None,
        instrument_id=None,
        instrument_tradingsymbol=None,
    )
