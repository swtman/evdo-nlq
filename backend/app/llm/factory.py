"""
Factory for creating LLMProvider instances.

WHAT A FACTORY IS
-----------------
A factory is simply a function (or class) whose only job is to create and
return objects. Instead of every caller knowing how to build a ClaudeProvider
(which API key to pass, how to set up the cache, etc.), they call this one
function and get back a ready-to-use provider.

This keeps construction logic in one place. If ClaudeProvider ever needs a new
argument, you change it here — not in every route or pipeline that uses it.

WHY IMPORTS ARE INSIDE THE FUNCTION (lazy imports)
---------------------------------------------------
Normally, imports sit at the top of the file and run as soon as the module is
loaded. Here, the imports for ClaudeProvider, GeminiProvider, and their SDKs
are placed *inside* each `case` branch instead.

This means:
- When `name="fake"`, the `anthropic` and `google.genai` packages are never
  imported at all — not even loaded into memory.
- This matters for unit tests: they run with `LLM_PROVIDER=fake` and should
  not need the Anthropic or Google SDKs installed. Lazy imports enforce that.

WHAT IS `match` / `case`?
--------------------------
`match` is Python 3.10+'s pattern matching — a cleaner alternative to a chain
of `if name == "claude": ... elif name == "gemini": ...` statements.

    match name:
        case "claude":   ...   # runs if name == "claude"
        case "gemini":   ...   # runs if name == "gemini"
        case _:          ...   # `_` is the wildcard — runs for anything else

It reads like a switch statement if you have seen those in other languages.
"""

from __future__ import annotations

from app.llm.base import LLMProvider

# Allowlist of permitted (provider, model) pairs.
# Ollama is absent intentionally — its models are discovered dynamically
# at runtime via the Ollama /api/tags endpoint and are only reachable on
# the local network, so static validation would be both fragile and unnecessary.
VALID_MODELS: dict[str, frozenset[str]] = {
    "fake": frozenset({"fake-v1"}),
    "claude": frozenset({"claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"}),
    "gemini": frozenset({"gemini-2.0-flash", "gemini-1.5-flash"}),
}


def get_provider(name: str, model: str) -> LLMProvider:
    """Build and return a fully configured LLMProvider.

    Called once per request by `_make_pipeline()` in `app/api/query.py`.
    The provider name and model string come directly from the frontend request,
    so the user controls which provider and model are used for each query.

    Parameters
    ----------
    name : str
        Provider identifier. One of: "claude", "gemini", "ollama", "fake".
    model : str
        Model name within that provider, e.g. "claude-haiku-4-5" or
        "gemini-2.0-flash". Passed through to the provider constructor.

    Returns
    -------
    LLMProvider
        A ready-to-use provider instance. The return type is the Protocol —
        the caller never sees ClaudeProvider or GeminiProvider directly,
        only the shared interface.

    Raises
    ------
    ValueError
        If `name` is not one of the known providers, or if `model` is not in
        the allowlist for `name`. The error message lists valid options.
    """
    # Reject models not in the static allowlist. Ollama is excluded from the
    # allowlist (its models are dynamic), so it passes through unchecked.
    if name in VALID_MODELS and model not in VALID_MODELS[name]:
        raise ValueError(
            f"Model {model!r} is not permitted for provider {name!r}. "
            f"Allowed: {sorted(VALID_MODELS[name])}"
        )
    match name:
        case "fake":
            # Imported here (not at top of file) so that running with
            # LLM_PROVIDER=fake never touches the anthropic or google packages.
            from app.llm.fake_provider import FakeProvider

            # FakeProvider needs no API key or cache — it has no network calls.
            return FakeProvider()

        case "claude":
            # These imports only run when name == "claude".
            from app.config import settings
            from app.llm.cache import DiskCache
            from app.llm.claude_provider import ClaudeProvider

            # A fresh DiskCache is created per request, but the underlying
            # files on disk persist across requests — that is where the
            # savings come from. The cache_dir and disabled flag come from
            # the shared `settings` object (read from .env).
            cache = DiskCache(
                cache_dir=settings.llm_cache_dir,
                disabled=settings.llm_cache_disabled,
            )
            return ClaudeProvider(model=model, api_key=settings.anthropic_api_key, cache=cache)

        case "gemini":
            # Same pattern as "claude" — lazy imports, fresh cache, inject key.
            from app.config import settings
            from app.llm.cache import DiskCache
            from app.llm.gemini_provider import GeminiProvider

            cache = DiskCache(
                cache_dir=settings.llm_cache_dir,
                disabled=settings.llm_cache_disabled,
            )
            return GeminiProvider(model=model, api_key=settings.gemini_api_key, cache=cache)

        case "ollama":
            # Lazy import so httpx and OllamaProvider are never touched
            # in tests that run with LLM_PROVIDER=fake.
            from app.config import settings
            from app.llm.cache import DiskCache
            from app.llm.ollama_provider import OllamaProvider

            cache = DiskCache(
                cache_dir=settings.llm_cache_dir,
                disabled=settings.llm_cache_disabled,
            )
            return OllamaProvider(
                model=model,
                base_url=settings.ollama_base_url,
                cache=cache,
            )

        case _:
            # `_` catches any value not matched above — the wildcard case.
            # `{name!r}` formats `name` with quotes around it in the message,
            # e.g.  Unknown LLM provider: 'gpt4'. Valid: 'claude', 'gemini', 'fake'
            raise ValueError(
                f"Unknown LLM provider: {name!r}. Valid: 'claude', 'gemini', 'ollama', 'fake'"
            )
