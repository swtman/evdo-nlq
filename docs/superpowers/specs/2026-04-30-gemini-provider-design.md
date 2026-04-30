# GeminiProvider Design

**Date:** 2026-04-30  
**Status:** Approved  
**Goal:** Add a free Google Gemini LLM provider so the backend can run live end-to-end tests and offer Gemini as a selectable provider in the UI, without requiring an Anthropic API key.

---

## Context

The backend has a clean `LLMProvider` protocol (`generate` + `stream`) with one real implementation (`ClaudeProvider`) and one fake (`FakeProvider`). The existing live test (`test_live_generate_returns_sparql`) requires `ANTHROPIC_API_KEY`. Adding `GeminiProvider` gives a zero-cost path to live pipeline testing and a second provider for the thesis comparison chapter.

Chosen provider: **Google Gemini** (`google-genai` SDK).  
- Free tier: 15 RPM, 1 million tokens/day on `gemini-2.0-flash`  
- Strong Greek + multilingual support (important: prompts and ontology labels are in Greek)  
- Native streaming via `generate_content_stream`

---

## Files Changed

| File | Action |
|---|---|
| `backend/app/llm/gemini_provider.py` | **Create** — `GeminiProvider` class |
| `backend/app/llm/factory.py` | Add `"gemini"` case to `get_provider()` |
| `backend/app/config.py` | Add `GEMINI_API_KEY` setting |
| `backend/app/api/providers.py` | Add Gemini entry to the static provider list |
| `backend/pyproject.toml` | Add `google-genai` to dependencies |
| `backend/.env.example` | Add `GEMINI_API_KEY=` line |
| `backend/tests/test_gemini_provider.py` | **Create** — unit tests + one `@pytest.mark.live` test |

---

## GeminiProvider

### Constructor

```python
class GeminiProvider:
    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._cache = cache
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0
```

Only `gemini_provider.py` may import `google.genai` — same isolation rule as `claude_provider.py` for `anthropic`.

### `generate()`

1. Check cache; return `LLMResponse(text=cached, input_tokens=0, output_tokens=0)` on hit.
2. Call `self._client.models.generate_content(model, contents=user, config=GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens))`.
3. Extract `response.text` and `response.usage_metadata.prompt_token_count` / `candidates_token_count`.
4. Write to cache, log token usage, return `LLMResponse`.

### `stream()`

1. Check cache; `yield cached; return` on hit.
2. Iterate `self._client.models.generate_content_stream(...)` with the same config.
3. For each chunk: if `chunk.text`, accumulate and `yield` it. Track `chunk.usage_metadata` — only the last chunk carries it.
4. After loop: write full text to cache, set `self.last_input_tokens` / `self.last_output_tokens` from the final chunk's usage metadata, log.

The `query.py` streaming endpoint reads these via `getattr(provider, "last_input_tokens", 0)` — no protocol change needed.

---

## Config

Add to `Settings` in `config.py`:

```python
gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
```

Add to `.env.example`:

```
GEMINI_API_KEY=          # get from https://aistudio.google.com/apikey (free)
```

---

## Factory

```python
case "gemini":
    from app.llm.cache import DiskCache
    from app.llm.gemini_provider import GeminiProvider
    from app.config import settings

    cache = DiskCache(cache_dir=settings.llm_cache_dir, disabled=settings.llm_cache_disabled)
    return GeminiProvider(model=model, api_key=settings.gemini_api_key, cache=cache)
```

Error message in the `case _` branch updated to include `'gemini'` in valid options.

---

## Providers Endpoint

```python
ProviderInfo(id="gemini", models=["gemini-2.0-flash", "gemini-1.5-flash"]),
```

---

## Tests

`test_gemini_provider.py` follows the same structure as `test_claude_provider.py`:

| Test | Type | What it checks |
|---|---|---|
| `test_generate_returns_llm_response` | unit | Returns correct `LLMResponse` |
| `test_generate_uses_cache_on_second_call` | unit | API called only once for same input |
| `test_generate_does_not_call_api_when_cache_hit` | unit | Cache hit skips API entirely |
| `test_stream_yields_tokens_and_sets_usage` | unit | Correct tokens yielded, `last_*` set |
| `test_live_generate_returns_sparql` | live | Skips if `GEMINI_API_KEY` not set; calls real API; asserts `"SELECT"` in output |

All unit tests mock `genai.Client` — no real API calls. Live test marked `@pytest.mark.live`.

---

## Dependency

```toml
"google-genai>=1.0"
```

Added to `[project.dependencies]` in `pyproject.toml`. Imported lazily in `factory.py` (same pattern as `anthropic`) so `LLM_PROVIDER=fake` tests never import it.
