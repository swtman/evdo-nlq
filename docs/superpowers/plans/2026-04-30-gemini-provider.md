# GeminiProvider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GeminiProvider` that implements the existing `LLMProvider` protocol so the backend can run live end-to-end tests and expose Gemini as a selectable provider in the UI without an Anthropic API key.

**Architecture:** Mirror `ClaudeProvider` exactly — wrap every call in `DiskCache`, set `last_input_tokens`/`last_output_tokens` after `stream()` completes, and isolate all `google.genai` imports inside `gemini_provider.py`. Register in `factory.py` under the key `"gemini"` and list in `providers.py` for the UI dropdown.

**Tech Stack:** `google-genai>=1.0` (new unified SDK), `pytest`, `unittest.mock`. All existing project tooling: `uv`, `ruff`, `mypy`, `pytest`.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/app/llm/gemini_provider.py` | `GeminiProvider` class — only file that imports `google.genai` |
| Create | `backend/tests/test_gemini_provider.py` | Unit tests (mocked) + one `@pytest.mark.live` test |
| Modify | `backend/pyproject.toml` | Add `google-genai>=1.0` dependency |
| Modify | `backend/app/config.py` | Add `GEMINI_API_KEY` setting |
| Modify | `backend/.env.example` | Add `GEMINI_API_KEY=` line |
| Modify | `backend/app/llm/factory.py` | Add `"gemini"` case to `get_provider()` |
| Modify | `backend/app/api/providers.py` | Add Gemini entry to static provider list |
| Modify | `backend/tests/test_factory.py` | Add `test_get_provider_gemini_returns_gemini_provider` |

---

## Task 1: Add dependency and config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add `google-genai` to pyproject.toml**

In `backend/pyproject.toml`, add to the `dependencies` list (keep alphabetical order is fine, just add after `fastapi`):

```toml
[project]
dependencies = [
    "anthropic>=0.49.0",
    "fastapi[standard]>=0.136.0",
    "google-genai>=1.0",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.14.0",
    "python-dotenv>=1.2.2",
    "rdflib>=7.6.0",
    "sparqlwrapper>=2.0.0",
    "sse-starlette>=2.0.0",
    "uvicorn[standard]>=0.45.0",
]
```

- [ ] **Step 2: Sync dependencies**

```bash
cd backend && uv sync
```

Expected: uv resolves and installs `google-genai` and its dependencies. No errors.

- [ ] **Step 3: Add `GEMINI_API_KEY` to Settings**

In `backend/app/config.py`, add one field to the `Settings` class after `anthropic_api_key`:

```python
class Settings(BaseSettings):
    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    graphdb_endpoint: str = Field(
        default="http://lod.csd.auth.gr:7200/repositories/Evdoxus",
        alias="GRAPHDB_ENDPOINT",
    )
    llm_cache_dir: str = Field(default=".llm_cache", alias="LLM_CACHE_DIR")
    llm_cache_disabled: bool = Field(default=False, alias="LLM_CACHE_DISABLED")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {"env_file": ".env", "populate_by_name": True}
```

- [ ] **Step 4: Add `GEMINI_API_KEY` to `.env.example`**

In `backend/.env.example`, add after the `ANTHROPIC_API_KEY` line:

```
# Anthropic API key (required if LLM_PROVIDER=claude)
ANTHROPIC_API_KEY=

# Google Gemini API key (required if LLM_PROVIDER=gemini)
# Get a free key at https://aistudio.google.com/apikey
GEMINI_API_KEY=
```

- [ ] **Step 5: Verify existing tests still pass**

```bash
cd backend && uv run pytest -v -m "not live"
```

Expected: all 34 tests pass. No import errors.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/.env.example
git commit -m "feat: add google-genai dependency and GEMINI_API_KEY config"
```

---

## Task 2: GeminiProvider — `generate()` with TDD

**Files:**
- Create: `backend/tests/test_gemini_provider.py`
- Create: `backend/app/llm/gemini_provider.py`

- [ ] **Step 1: Write failing tests for `generate()`**

Create `backend/tests/test_gemini_provider.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from app.llm.base import LLMResponse
from app.llm.cache import DiskCache


def _make_provider(tmp_path, model="gemini-2.0-flash"):
    from app.llm.gemini_provider import GeminiProvider

    cache = DiskCache(str(tmp_path / "cache"))
    return GeminiProvider(model=model, api_key="test-key", cache=cache)


def _mock_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = input_tokens
    resp.usage_metadata.candidates_token_count = output_tokens
    return resp


def test_generate_returns_llm_response(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(
        provider._client.models, "generate_content", return_value=_mock_response("SELECT *")
    ):
        result = provider.generate("system", "user")
    assert isinstance(result, LLMResponse)
    assert result.text == "SELECT *"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_generate_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(
        provider._client.models,
        "generate_content",
        return_value=_mock_response("SELECT *"),
    ) as mock_generate:
        provider.generate("system", "user")
        provider.generate("system", "user")
    assert mock_generate.call_count == 1


def test_generate_does_not_call_api_when_cache_hit(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")
    with patch.object(provider._client.models, "generate_content") as mock_generate:
        result = provider.generate("system", "user")
    mock_generate.assert_not_called()
    assert result.text == "CACHED SPARQL"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_gemini_provider.py -v
```

Expected: 3 errors — `ModuleNotFoundError: No module named 'app.llm.gemini_provider'`.

- [ ] **Step 3: Implement `GeminiProvider` with `generate()`**

Create `backend/app/llm/gemini_provider.py`:

```python
"""Google Gemini implementation of LLMProvider.

Only this file may import google.genai — all other modules must go through the
LLMProvider protocol to keep the provider abstraction honest.
"""

from __future__ import annotations

import logging
from typing import Iterator

import google.genai as genai
from google.genai import types

from app.llm.base import LLMResponse
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Google Gemini implementation. Wraps every call with a disk cache."""

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._cache = cache
        # Set after stream() completes — read by the streaming endpoint for the done event.
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Generate a response. Returns cached result if available."""
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        text = response.text
        usage = response.usage_metadata
        self._cache.set(system, user, self._model, text)

        logger.info(
            "Gemini [%s] input=%d output=%d",
            self._model,
            usage.prompt_token_count,
            usage.candidates_token_count,
        )
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
        )

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]:
        """Stub — implemented in Task 3."""
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && uv run pytest tests/test_gemini_provider.py -v -k "generate"
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/gemini_provider.py backend/tests/test_gemini_provider.py
git commit -m "feat: implement GeminiProvider.generate() with cache and tests"
```

---

## Task 3: GeminiProvider — `stream()` with TDD

**Files:**
- Modify: `backend/tests/test_gemini_provider.py`
- Modify: `backend/app/llm/gemini_provider.py`

- [ ] **Step 1: Write the failing stream test**

Append to `backend/tests/test_gemini_provider.py`:

```python
def test_stream_yields_tokens_and_sets_usage(tmp_path):
    provider = _make_provider(tmp_path)

    def _make_chunk(text, prompt_tokens=None, candidate_tokens=None):
        chunk = MagicMock()
        chunk.text = text
        if prompt_tokens is not None:
            chunk.usage_metadata = MagicMock()
            chunk.usage_metadata.prompt_token_count = prompt_tokens
            chunk.usage_metadata.candidates_token_count = candidate_tokens
        else:
            chunk.usage_metadata = None
        return chunk

    chunks = [
        _make_chunk("PREFIX"),
        _make_chunk(" evdx:"),
        _make_chunk("SELECT *", prompt_tokens=80, candidate_tokens=30),
    ]

    with patch.object(
        provider._client.models,
        "generate_content_stream",
        return_value=iter(chunks),
    ):
        result = list(provider.stream("system", "user"))

    assert result == ["PREFIX", " evdx:", "SELECT *"]
    assert provider.last_input_tokens == 80
    assert provider.last_output_tokens == 30


def test_stream_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")
    with patch.object(provider._client.models, "generate_content_stream") as mock_stream:
        result = list(provider.stream("system", "user"))
    mock_stream.assert_not_called()
    assert result == ["CACHED SPARQL"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_gemini_provider.py::test_stream_yields_tokens_and_sets_usage tests/test_gemini_provider.py::test_stream_uses_cache_on_second_call -v
```

Expected: 2 failures — `NotImplementedError`.

- [ ] **Step 3: Replace the `stream()` stub with the real implementation**

Replace the `stream` method in `backend/app/llm/gemini_provider.py`:

```python
    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]:
        """Yield raw text tokens from the Gemini streaming API.

        After the generator is exhausted, last_input_tokens and last_output_tokens
        are set so callers can include them in the SSE 'done' event.
        """
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            yield cached
            return

        full_text = ""
        last_usage = None
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        ):
            if chunk.text:
                full_text += chunk.text
                yield chunk.text
            if chunk.usage_metadata:
                last_usage = chunk.usage_metadata

        self._cache.set(system, user, self._model, full_text)
        if last_usage is not None:
            self.last_input_tokens = last_usage.prompt_token_count or 0
            self.last_output_tokens = last_usage.candidates_token_count or 0
        logger.info(
            "Gemini stream [%s] input=%d output=%d",
            self._model,
            self.last_input_tokens,
            self.last_output_tokens,
        )
```

- [ ] **Step 4: Run all GeminiProvider tests**

```bash
cd backend && uv run pytest tests/test_gemini_provider.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run full test suite to catch regressions**

```bash
cd backend && uv run pytest -v -m "not live"
```

Expected: all 34 existing tests + 5 new = 39 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/llm/gemini_provider.py backend/tests/test_gemini_provider.py
git commit -m "feat: implement GeminiProvider.stream() with cache and tests"
```

---

## Task 4: Wire factory and providers endpoint

**Files:**
- Modify: `backend/app/llm/factory.py`
- Modify: `backend/app/api/providers.py`
- Modify: `backend/tests/test_factory.py`

- [ ] **Step 1: Write the failing factory test**

Append to `backend/tests/test_factory.py`:

```python
def test_get_provider_gemini_returns_gemini_provider():
    from unittest.mock import patch, MagicMock
    from app.llm.gemini_provider import GeminiProvider

    with patch("app.llm.gemini_provider.genai") as mock_genai:
        mock_genai.Client.return_value = MagicMock()
        provider = get_provider("gemini", "gemini-2.0-flash")

    assert isinstance(provider, GeminiProvider)
    assert isinstance(provider, LLMProvider)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_factory.py::test_get_provider_gemini_returns_gemini_provider -v
```

Expected: FAIL — `ValueError: Unknown LLM provider: 'gemini'`.

- [ ] **Step 3: Add the `"gemini"` case to `factory.py`**

Replace `backend/app/llm/factory.py` with:

```python
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
```

- [ ] **Step 4: Run factory test to confirm it passes**

```bash
cd backend && uv run pytest tests/test_factory.py -v
```

Expected: all 3 factory tests PASS.

- [ ] **Step 5: Add Gemini to the providers endpoint**

In `backend/app/api/providers.py`, update `_PROVIDERS`:

```python
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
```

- [ ] **Step 6: Run the full test suite**

```bash
cd backend && uv run pytest -v -m "not live"
```

Expected: all 40 tests PASS (39 from previous tasks + 1 new factory test).

- [ ] **Step 7: Commit**

```bash
git add backend/app/llm/factory.py backend/app/api/providers.py backend/tests/test_factory.py
git commit -m "feat: register GeminiProvider in factory and providers endpoint"
```

---

## Task 5: Add live test

**Files:**
- Modify: `backend/tests/test_gemini_provider.py`

- [ ] **Step 1: Append the live test**

Append to `backend/tests/test_gemini_provider.py`:

```python
@pytest.mark.live
def test_live_generate_returns_sparql(tmp_path):
    """Requires GEMINI_API_KEY in .env. Run with: uv run pytest -m live"""
    import os
    from app.llm.gemini_provider import GeminiProvider

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        pytest.skip("GEMINI_API_KEY not set")
    cache = DiskCache(str(tmp_path / "cache"))
    provider = GeminiProvider(model="gemini-2.0-flash", api_key=key, cache=cache)
    result = provider.generate("Respond with only: SELECT * WHERE {}", "test")
    assert "SELECT" in result.text
    assert result.input_tokens > 0
```

- [ ] **Step 2: Confirm the live test is skipped in the default run**

```bash
cd backend && uv run pytest tests/test_gemini_provider.py -v -m "not live"
```

Expected: 5 unit tests PASS, 1 live test SKIPPED (or not collected).

- [ ] **Step 3: Set up your key and run the live test**

Copy `.env.example` to `.env` if you haven't already, then add your key:

```
GEMINI_API_KEY=your-key-here   # from https://aistudio.google.com/apikey
```

Then run:

```bash
cd backend && uv run pytest tests/test_gemini_provider.py::test_live_generate_returns_sparql -v -m live
```

Expected: PASS — `SELECT` appears in the output, `input_tokens > 0`.

- [ ] **Step 4: Run the full end-to-end live pipeline test**

This tests the entire path: Gemini → SPARQL → GraphDB → results.

```bash
cd backend && uv run pytest -m live -v
```

Expected: both live tests PASS — `test_live_generate_returns_sparql` (Gemini) and `test_live_execute_returns_results` (GraphDB).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_gemini_provider.py
git commit -m "test: add live test for GeminiProvider"
```

---

## Final verification

- [ ] **Lint and format**

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
```

Expected: no errors.

- [ ] **Type check**

```bash
cd backend && uv run mypy app
```

Expected: no errors. (Note: `google-genai` ships with type stubs.)

- [ ] **Full non-live suite**

```bash
cd backend && uv run pytest -v -m "not live"
```

Expected: 40 tests PASS, 0 FAIL.
