"""
GET /providers — serves the list of LLM providers and models for the UI dropdown.

Static providers (claude, gemini, fake) are always included.
The `ollama` provider is included dynamically: if the Ollama service is
reachable (checked via GET /api/tags with a 1-second timeout), its installed
models are fetched and exposed. If Ollama is unreachable, it is silently
omitted so the UI only shows providers that actually work.
"""

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderInfo(BaseModel):
    """Describes one LLM provider and its available models.

    Fields
    ------
    id : str
        Provider identifier matching what factory.py accepts.
    models : list[str]
        Ordered list of model name strings; first is shown as default in UI.
    """

    id: str
    models: list[str]


class ProvidersResponse(BaseModel):
    """Response body for GET /providers."""

    providers: list[ProviderInfo]


# Static providers always available regardless of env/keys.
_STATIC_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(
        id="claude",
        models=["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"],
    ),
    ProviderInfo(
        id="gemini",
        models=["gemini-2.5-flash-lite"],
    ),
    ProviderInfo(id="fake", models=["fake-v1"]),
]


def _get_ollama_provider() -> ProviderInfo | None:
    """Return a ProviderInfo for Ollama if the local service is reachable.

    Calls GET /api/tags on the configured Ollama URL with a 1-second timeout.
    Returns None (without raising) if Ollama is unreachable or has no models.
    """
    try:
        resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if not models:
            return None
        return ProviderInfo(id="ollama", models=models)
    except Exception:
        logger.debug("Ollama not reachable at %s", settings.ollama_base_url)
        return None


@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    """Return available LLM providers and their models.

    Static providers (claude, gemini, fake) are always present.
    Ollama is appended only when reachable.
    """
    providers = list(_STATIC_PROVIDERS)
    ollama = _get_ollama_provider()
    if ollama:
        providers.append(ollama)
    return ProvidersResponse(providers=providers)
