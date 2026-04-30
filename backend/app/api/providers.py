"""GET /providers — returns the list of LLM providers and models for the UI dropdown."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ProviderInfo(BaseModel):
    id: str
    models: list[str]


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]


_PROVIDERS = [
    ProviderInfo(
        id="claude",
        models=["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"],
    ),
    ProviderInfo(
        id="gemini",
        models=["gemini-2.0-flash", "gemini-1.5-flash"],
    ),
    ProviderInfo(id="fake", models=["fake-v1"]),
]


@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    """Return the static list of available LLM providers and their models."""
    return ProvidersResponse(providers=_PROVIDERS)
