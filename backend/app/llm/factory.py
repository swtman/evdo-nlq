"""Creates LLMProvider instances by name.

Claude and Gemini providers are imported lazily to avoid requiring their SDKs
when running with LLM_PROVIDER=fake (e.g. in unit tests).
"""

from __future__ import annotations

from app.llm.base import LLMProvider


def get_provider(name: str, model: str) -> LLMProvider:
    """Return a configured LLMProvider for the given provider name and model."""
    match name:
        case "fake":
            from app.llm.fake_provider import FakeProvider

            return FakeProvider()
        case "claude":
            from app.llm.cache import DiskCache
            from app.llm.claude_provider import ClaudeProvider
            from app.config import settings

            cache = DiskCache(
                cache_dir=settings.llm_cache_dir,
                disabled=settings.llm_cache_disabled,
            )
            return ClaudeProvider(model=model, api_key=settings.anthropic_api_key, cache=cache)
        case "gemini":
            from app.llm.cache import DiskCache
            from app.llm.gemini_provider import GeminiProvider
            from app.config import settings

            cache = DiskCache(
                cache_dir=settings.llm_cache_dir,
                disabled=settings.llm_cache_disabled,
            )
            return GeminiProvider(model=model, api_key=settings.gemini_api_key, cache=cache)
        case _:
            raise ValueError(
                f"Unknown LLM provider: {name!r}. Valid: 'claude', 'gemini', 'fake'"
            )
