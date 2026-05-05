"""
GET /providers — serves the list of LLM providers and models for the UI dropdown.

WHY THIS ENDPOINT EXISTS
-------------------------
The React frontend needs to know which providers (claude, gemini, fake) and
which models within each provider are available, so it can populate the
dropdown before the user submits a question.

Rather than hard-coding that list in both the frontend AND the backend (two
sources of truth that could drift out of sync), the backend owns the list and
the frontend fetches it once at startup via GET /providers.

WHY THE LIST IS STATIC
-----------------------
The available providers and models are a deployment-time choice, not a
runtime-discovered one. Adding a new model means updating this file and
redeploying — there is no auto-discovery from the LLM APIs. This keeps the
endpoint trivially fast (no network calls, no I/O) and the available options
explicit and auditable.

IMPORTANT: this list is completely independent of factory.py.
The factory decides how to construct a provider; this file decides what the
UI shows. If you add a provider to factory.py but not here, users cannot
select it from the dropdown (though they could still send it manually in the
request body). If you add one here but not in factory.py, selecting it will
produce a ValueError at request time.
"""

from fastapi import APIRouter
from pydantic import BaseModel

# APIRouter lets each file define its own routes independently.
# main.py mounts this router on the app with app.include_router(router),
# which registers all routes defined here. The final URL is /providers
# because no prefix is added at the mount site.
router = APIRouter()


class ProviderInfo(BaseModel):
    """Describes one LLM provider and its available models.

    WHAT IS A Pydantic BaseModel?
    ------------------------------
    Pydantic models are Python classes that validate their fields
    automatically. When FastAPI serializes a response, it calls Pydantic
    to convert the object to a JSON-compatible dict and validate the shape.
    A `BaseModel` is essentially a typed, self-validating data container.

    Fields
    ------
    id : str
        The provider identifier string. Must match what factory.py accepts,
        e.g. "claude", "gemini", "fake".
    models : list[str]
        Ordered list of model name strings within this provider. The first
        entry is shown as the default in the UI dropdown.
    """

    id: str
    models: list[str]


class ProvidersResponse(BaseModel):
    """The full response body for GET /providers.

    Wraps the list of providers in a named field so the JSON response
    has a clear top-level key:

        { "providers": [ { "id": "claude", "models": [...] }, ... ] }

    FastAPI uses this class as `response_model` — it validates the return
    value of list_providers() against this schema and generates an accurate
    OpenAPI entry for this endpoint automatically.
    """

    providers: list[ProviderInfo]


# The static list of available providers and their models.
# Built once when the module is imported — never changes while the server runs.
# The `fake` provider is intentionally included so UI iteration and manual
# testing work without API keys.
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
    """Return the static list of available LLM providers and their models.

    This is a plain synchronous function (no `async`). FastAPI runs sync
    route handlers in a background thread automatically, so this is correct —
    there is nothing async to await here since no I/O happens.

    The `response_model=ProvidersResponse` parameter on the decorator tells
    FastAPI to validate the return value and generate OpenAPI documentation
    for this endpoint.
    """
    return ProvidersResponse(providers=_PROVIDERS)
