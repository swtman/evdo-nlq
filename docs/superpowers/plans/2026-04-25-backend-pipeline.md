# NLQ Backend Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend that accepts a natural-language question, generates SPARQL via an LLM, executes it against EvdoGraph, and returns results — with a streaming SSE endpoint and per-request provider selection.

**Architecture:** Thin-slice order: get `POST /query` working end-to-end with `FakeProvider` first, then layer in `ClaudeProvider` + disk cache, then add `POST /query/stream` (SSE). Each task produces runnable, testable code.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pydantic-settings, anthropic SDK, SPARQLWrapper, rdflib (SPARQL validation), sse-starlette, pytest, uv.

---

## File map

| File | Responsibility |
|---|---|
| `backend/app/main.py` | FastAPI app creation, CORS middleware, router mounting |
| `backend/app/config.py` | Pydantic Settings class, reads `.env` |
| `backend/app/api/query.py` | `POST /query` (JSON) and `POST /query/stream` (SSE) |
| `backend/app/api/providers.py` | `GET /providers` — static provider+model list |
| `backend/app/llm/base.py` | `LLMProvider` protocol, `LLMResponse` dataclass |
| `backend/app/llm/fake_provider.py` | Returns canned SPARQL; fake stream (no network) |
| `backend/app/llm/claude_provider.py` | Anthropic SDK: `generate` + real `stream` |
| `backend/app/llm/cache.py` | Disk cache keyed on `sha256(system+user+model)` |
| `backend/app/llm/factory.py` | `get_provider(name, model) → LLMProvider` |
| `backend/app/sparql/client.py` | `validate_sparql(q)` + `SparqlClient.execute(q)` |
| `backend/app/ontology/loader.py` | `load_summary()` — reads static file, module-level cache |
| `backend/app/prompts/loader.py` | `load(name, version)` + `fill(template, **kwargs)` |
| `backend/tests/conftest.py` | `client` fixture |
| `backend/tests/test_query_endpoint.py` | POST /query integration tests |
| `backend/tests/test_prompt_loader.py` | Prompt load + fill tests |
| `backend/tests/test_sparql_client.py` | SPARQL validate + execute tests |
| `backend/tests/test_cache.py` | Cache hit / miss / disabled tests |
| `prompts/ontology-summary.md` | Compact EvdoGraph schema for prompt injection |
| `prompts/nl-to-sparql-retry-v1.md` | Retry system prompt (error injection) |

All commands below assume `cd backend` before running.

---

## Task 1: Project setup

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/app/llm/__init__.py`, `backend/app/sparql/__init__.py`, `backend/app/ontology/__init__.py`, `backend/app/prompts/__init__.py`, `backend/tests/__init__.py`

- [ ] **Step 1: Add sse-starlette dependency and pytest config to pyproject.toml**

Replace the full `pyproject.toml` with:

```toml
[project]
name = "backend"
version = "0.1.0"
description = "EvdoGraph NLQ backend — FastAPI service"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.49.0",
    "fastapi>=0.136.0",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.14.0",
    "python-dotenv>=1.2.2",
    "rdflib>=7.6.0",
    "sparqlwrapper>=2.0.0",
    "sse-starlette>=2.0.0",
    "uvicorn[standard]>=0.45.0",
]

[dependency-groups]
dev = [
    "httpx>=0.28.0",
    "mypy>=1.20.2",
    "pytest>=9.0.3",
    "ruff>=0.15.11",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "live: marks tests requiring live API keys and network (skip with '-m not live')",
]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Install updated dependencies**

```bash
uv sync
```

Expected: no errors, `sse-starlette` appears in the lock.

- [ ] **Step 3: Create package __init__.py files**

Create these six empty files (one command each):

```bash
mkdir -p app/api app/llm app/sparql app/ontology app/prompts tests
touch app/__init__.py app/api/__init__.py app/llm/__init__.py
touch app/sparql/__init__.py app/ontology/__init__.py app/prompts/__init__.py
touch tests/__init__.py
```

- [ ] **Step 4: Verify pytest can be invoked**

```bash
uv run pytest --collect-only
```

Expected: `no tests ran` (0 errors — just no test files yet).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock app/ tests/
git commit -m "chore: project setup — package structure, sse-starlette, pytest config"
```

---

## Task 2: config.py

**Files:**
- Create: `backend/app/config.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_config.py`:

```python
from app.config import settings


def test_settings_has_required_fields():
    assert hasattr(settings, "llm_provider")
    assert hasattr(settings, "llm_model")
    assert hasattr(settings, "graphdb_endpoint")
    assert hasattr(settings, "llm_cache_dir")
    assert hasattr(settings, "llm_cache_disabled")
    assert hasattr(settings, "frontend_origin")
    assert hasattr(settings, "log_level")


def test_settings_defaults():
    assert settings.llm_provider == "claude"
    assert settings.llm_model == "claude-haiku-4-5"
    assert "Evdoxus" in settings.graphdb_endpoint
    assert settings.llm_cache_dir == ".llm_cache"
    assert settings.llm_cache_disabled is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ImportError: No module named 'app.config'`

- [ ] **Step 3: Implement config.py**

Create `backend/app/config.py`:

```python
"""Application settings — all values are env-backed via .env."""
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    graphdb_endpoint: str = Field(
        default="http://lod.csd.auth.gr:7200/repositories/Evdoxus",
        alias="GRAPHDB_ENDPOINT",
    )
    llm_cache_dir: str = Field(default=".llm_cache", alias="LLM_CACHE_DIR")
    llm_cache_disabled: bool = Field(default=False, alias="LLM_CACHE_DISABLED")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add Pydantic settings (config.py)"
```

---

## Task 3: llm/base.py

**Files:**
- Create: `backend/app/llm/base.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_llm_base.py`:

```python
from dataclasses import fields
from app.llm.base import LLMResponse, LLMProvider
from typing import Iterator, runtime_checkable
from typing import Protocol


def test_llm_response_is_dataclass():
    r = LLMResponse(text="SELECT * WHERE {}", input_tokens=10, output_tokens=5)
    assert r.text == "SELECT * WHERE {}"
    assert r.input_tokens == 10
    assert r.output_tokens == 5


def test_llm_provider_is_protocol():
    # Protocol — not instantiable directly, but importable
    assert hasattr(LLMProvider, "generate")
    assert hasattr(LLMProvider, "stream")
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_llm_base.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement llm/base.py**

Create `backend/app/llm/base.py`:

```python
"""LLMProvider protocol and response dataclass shared by all provider implementations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class LLMProvider(Protocol):
    def generate(
        self, system: str, user: str, *, max_tokens: int = 1024
    ) -> LLMResponse: ...

    def stream(
        self, system: str, user: str, *, max_tokens: int = 1024
    ) -> Iterator[str]: ...
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_llm_base.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add app/llm/base.py tests/test_llm_base.py
git commit -m "feat: add LLMProvider protocol and LLMResponse dataclass"
```

---

## Task 4: llm/fake_provider.py

**Files:**
- Create: `backend/app/llm/fake_provider.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_fake_provider.py`:

```python
from app.llm.fake_provider import FakeProvider
from app.llm.base import LLMResponse


_SYSTEM = "You are a SPARQL generator."
_USER = "List all books."


def test_generate_returns_llm_response():
    provider = FakeProvider()
    result = provider.generate(_SYSTEM, _USER)
    assert isinstance(result, LLMResponse)
    assert "PREFIX evdx:" in result.text
    assert "SELECT" in result.text
    assert result.input_tokens >= 0
    assert result.output_tokens >= 0


def test_stream_yields_characters_that_assemble_to_generate_output():
    provider = FakeProvider()
    streamed = "".join(provider.stream(_SYSTEM, _USER))
    expected = provider.generate(_SYSTEM, _USER).text
    assert streamed == expected


def test_fake_provider_satisfies_protocol():
    from app.llm.base import LLMProvider
    provider = FakeProvider()
    assert isinstance(provider, LLMProvider)
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_fake_provider.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement fake_provider.py**

Create `backend/app/llm/fake_provider.py`:

```python
"""FakeProvider — returns canned SPARQL with no network calls.

Use this for all unit tests and frontend development to avoid burning API tokens.
"""
from __future__ import annotations

from typing import Iterator

from app.llm.base import LLMProvider, LLMResponse

_CANNED_SPARQL = (
    "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
    "SELECT DISTINCT ?title WHERE {\n"
    "  ?book a evdx:Book ;\n"
    "        evdx:title ?title .\n"
    "}\n"
    "LIMIT 10"
)


class FakeProvider:
    """No-network LLMProvider for tests and frontend development."""

    def generate(
        self, system: str, user: str, *, max_tokens: int = 1024
    ) -> LLMResponse:
        return LLMResponse(
            text=_CANNED_SPARQL,
            input_tokens=42,
            output_tokens=len(_CANNED_SPARQL.split()),
        )

    def stream(
        self, system: str, user: str, *, max_tokens: int = 1024
    ) -> Iterator[str]:
        """Yield the canned SPARQL one character at a time to simulate streaming."""
        yield from _CANNED_SPARQL
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_fake_provider.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add app/llm/fake_provider.py tests/test_fake_provider.py
git commit -m "feat: add FakeProvider for tests and frontend dev"
```

---

## Task 5: prompts/loader.py + ontology/loader.py + create static files

**Files:**
- Create: `backend/app/prompts/loader.py`
- Create: `backend/app/ontology/loader.py`
- Create: `prompts/ontology-summary.md`
- Test: `backend/tests/test_prompt_loader.py`

- [ ] **Step 1: Create prompts/ontology-summary.md** (at repo root level `prompts/`, not inside backend)

Create `prompts/ontology-summary.md`:

```markdown
PREFIX evdx: <https://w3id.org/evdoxus#>

Main classes:
- evdx:University   — a Greek university (46 instances)
- evdx:Department   — a department within a university (732); linked via evdx:hasDepartment
- evdx:Course       — a study programme / curriculum (9,516); linked to dept via evdx:hasCourse
- evdx:Module       — a single course offering in a year/semester (535,143); linked to programme via evdx:hasModule
- evdx:Book         — a textbook (40,529); linked to module via evdx:hasBook

Key properties:
- evdx:hasDepartment   University → Department
- evdx:hasCourse       Department → Course (study programme)
- evdx:hasModule       Course → Module (course offering)
- evdx:hasBook         Module → Book
- evdx:title           LearningEntity (Book or Module) → string
- evdx:name            AcademicEntity (Dept or University) → string
- evdx:semester        Module → string (e.g. "1", "2")
- evdx:year            Course → integer (e.g. 2021)
- evdx:hasCode         LearningEntity → string (Eudoxus book code)
- evdx:hasURL          LearningEntity → URL

IMPORTANT: evdx:Module is what people call a "course".
evdx:Course is a study programme (e.g. "Computer Science BSc") — NOT a single course.
Always prefer the evdx: namespace over aliases (teach:, schema:, aiiso:, etc.).
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_prompt_loader.py`:

```python
import re
import pytest
from pathlib import Path
from app.prompts.loader import load, fill


def test_load_returns_system_section_of_nl_to_sparql_v1():
    """The real nl-to-sparql-v1.md must be present in prompts/."""
    text = load("nl-to-sparql", 1)
    assert "{ontology_summary}" in text
    assert "SPARQL" in text
    # Should NOT include the User or Notes sections
    assert "# User" not in text
    assert "# Notes" not in text


def test_load_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        load("nonexistent-prompt", 99)


def test_fill_substitutes_known_slots():
    template = "Hello {name}, you asked: {question}"
    result = fill(template, name="World", question="ποια βιβλία;")
    assert result == "Hello World, you asked: ποια βιβλία;"


def test_fill_leaves_unknown_slots_unchanged():
    """SPARQL curly braces and unrecognised slots must not be consumed."""
    template = "WHERE { ?s ?p ?o } {unknown_slot}"
    result = fill(template, known="value")
    assert "{ ?s ?p ?o }" in result
    assert "{unknown_slot}" in result


def test_fill_handles_sparql_word_braces():
    """Single-word slots that look like SPARQL vars should not be wrongly substituted."""
    template = "FILTER (?year >= 2020) {ontology_summary}"
    result = fill(template, ontology_summary="schema here")
    assert "FILTER (?year >= 2020)" in result
    assert "schema here" in result
```

- [ ] **Step 3: Run to verify it fails**

```bash
uv run pytest tests/test_prompt_loader.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Implement prompts/loader.py**

Create `backend/app/prompts/loader.py`:

```python
"""Loads versioned prompt templates from the top-level prompts/ directory."""
from __future__ import annotations

import re
from pathlib import Path

# prompts/ lives four levels up from this file (backend/app/prompts/loader.py → repo root)
_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


def load(name: str, version: int) -> str:
    """Return the '# System' section of a versioned prompt template.

    Strips YAML frontmatter and discards all sections after '# System'.
    """
    path = _PROMPTS_DIR / f"{name}-v{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")

    raw = path.read_text(encoding="utf-8")

    # Strip YAML frontmatter (--- ... ---)
    raw = re.sub(r"\A---\n.*?\n---\n*", "", raw, flags=re.DOTALL)

    # Extract the '# System' section up to the next top-level heading or EOF
    m = re.search(r"^# System\n(.*?)(?=^# |\Z)", raw, re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError(f"No '# System' section found in {path.name}")

    return m.group(1).strip()


def fill(template: str, **kwargs: str) -> str:
    """Substitute {slot} placeholders in a prompt template.

    Only replaces {word} patterns where 'word' is a key in kwargs.
    Curly braces containing spaces or special chars (e.g. SPARQL patterns) are untouched.
    """
    return re.sub(
        r"\{(\w+)\}",
        lambda m: kwargs.get(m.group(1), m.group(0)),
        template,
    )
```

- [ ] **Step 5: Implement ontology/loader.py**

Create `backend/app/ontology/loader.py`:

```python
"""Loads the static EvdoGraph ontology summary from prompts/ontology-summary.md.

The summary is read once and cached in a module-level variable for the process lifetime.
No SPARQL is executed at startup — the ontology does not change.
"""
from __future__ import annotations

from pathlib import Path

_ONTOLOGY_FILE = Path(__file__).parent.parent.parent.parent / "prompts" / "ontology-summary.md"

_cached: str | None = None


def load_summary() -> str:
    """Return the compact ontology schema string. Cached after first read."""
    global _cached
    if _cached is None:
        if not _ONTOLOGY_FILE.exists():
            raise FileNotFoundError(f"Ontology summary not found: {_ONTOLOGY_FILE}")
        _cached = _ONTOLOGY_FILE.read_text(encoding="utf-8")
    return _cached
```

- [ ] **Step 6: Run to verify it passes**

```bash
uv run pytest tests/test_prompt_loader.py -v
```

Expected: `5 passed`

- [ ] **Step 7: Commit**

```bash
git add app/prompts/loader.py app/ontology/loader.py tests/test_prompt_loader.py
git commit -m "feat: prompt loader, ontology loader, ontology-summary.md"
# Note: prompts/ontology-summary.md is committed from repo root
git -C .. add prompts/ontology-summary.md
git -C .. commit -m "feat: add compact ontology summary for LLM prompts"
```

---

## Task 6: sparql/client.py

**Files:**
- Create: `backend/app/sparql/client.py`
- Test: `backend/tests/test_sparql_client.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_sparql_client.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from app.sparql.client import SparqlClient, SparqlResult, validate_sparql


_VALID_SPARQL = """
PREFIX evdx: <https://w3id.org/evdoxus#>
SELECT DISTINCT ?title WHERE {
  ?book a evdx:Book ;
        evdx:title ?title .
}
LIMIT 10
"""

_INVALID_SPARQL = "SELECT WHERE { broken syntax !!!"


def test_validate_sparql_returns_none_for_valid_query():
    assert validate_sparql(_VALID_SPARQL) is None


def test_validate_sparql_returns_error_string_for_invalid_query():
    error = validate_sparql(_INVALID_SPARQL)
    assert isinstance(error, str)
    assert len(error) > 0


def test_execute_returns_sparql_result():
    raw_response = {
        "head": {"vars": ["title"]},
        "results": {"bindings": [{"title": {"value": "Αλγόριθμοι"}}]},
    }
    mock_wrapper = MagicMock()
    mock_wrapper.query.return_value.convert.return_value = raw_response

    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        client = SparqlClient("http://example.com/sparql")
        result = client.execute(_VALID_SPARQL)

    assert isinstance(result, SparqlResult)
    assert result.columns == ["title"]
    assert result.rows == [{"title": "Αλγόριθμοι"}]


def test_execute_raises_runtime_error_on_sparql_failure():
    mock_wrapper = MagicMock()
    mock_wrapper.query.side_effect = Exception("Connection refused")

    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        client = SparqlClient("http://example.com/sparql")
        with pytest.raises(RuntimeError, match="SPARQL execution failed"):
            client.execute(_VALID_SPARQL)


def test_execute_handles_missing_binding_columns():
    """If a binding doesn't include a variable, the value should be None."""
    raw_response = {
        "head": {"vars": ["title", "code"]},
        "results": {"bindings": [{"title": {"value": "Αλγόριθμοι"}}]},
    }
    mock_wrapper = MagicMock()
    mock_wrapper.query.return_value.convert.return_value = raw_response

    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        client = SparqlClient("http://example.com/sparql")
        result = client.execute(_VALID_SPARQL)

    assert result.rows[0]["code"] is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_sparql_client.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement sparql/client.py**

Create `backend/app/sparql/client.py`:

```python
"""SPARQL client for EvdoGraph's GraphDB endpoint.

validate_sparql() uses rdflib for offline parse checking (no network).
SparqlClient.execute() makes a live HTTP call to GraphDB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from SPARQLWrapper import JSON, SPARQLWrapper

logger = logging.getLogger(__name__)


@dataclass
class SparqlResult:
    columns: list[str]
    rows: list[dict[str, Any]]


def validate_sparql(query: str) -> str | None:
    """Return a parse error string if the query is invalid, or None if valid."""
    from rdflib.plugins.sparql.parser import parseQuery

    try:
        parseQuery(query)
        return None
    except Exception as exc:
        return str(exc)


class SparqlClient:
    """HTTP client for a SPARQL 1.1 endpoint (read-only)."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    def execute(self, query: str) -> SparqlResult:
        """Execute a SELECT query and return structured results."""
        wrapper = SPARQLWrapper(self._endpoint)
        wrapper.setQuery(query)
        wrapper.setReturnFormat(JSON)
        try:
            raw = wrapper.query().convert()
        except Exception as exc:
            logger.error("SPARQL execution failed: %s", exc)
            raise RuntimeError(f"SPARQL execution failed: {exc}") from exc

        columns: list[str] = raw.get("head", {}).get("vars", [])
        bindings: list[dict] = raw.get("results", {}).get("bindings", [])
        rows = [
            {col: b[col]["value"] if col in b else None for col in columns}
            for b in bindings
        ]
        return SparqlResult(columns=columns, rows=rows)
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_sparql_client.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add app/sparql/client.py tests/test_sparql_client.py
git commit -m "feat: SPARQL client with rdflib validation and SPARQLWrapper execution"
```

---

## Task 7: llm/factory.py (fake-only)

**Files:**
- Create: `backend/app/llm/factory.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_factory.py`:

```python
import pytest
from app.llm.factory import get_provider
from app.llm.fake_provider import FakeProvider
from app.llm.base import LLMProvider


def test_get_provider_fake_returns_fake_provider():
    provider = get_provider("fake", "fake-v1")
    assert isinstance(provider, FakeProvider)
    assert isinstance(provider, LLMProvider)


def test_get_provider_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("nonexistent", "model-x")
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_factory.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement factory.py**

Create `backend/app/llm/factory.py`:

```python
"""Creates LLMProvider instances by name.

Claude provider is imported lazily to avoid requiring the anthropic SDK
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
        case _:
            raise ValueError(f"Unknown LLM provider: {name!r}. Valid: 'claude', 'fake'")
```

- [ ] **Step 4: Run to verify fake test passes (claude will fail — that's expected)**

```bash
uv run pytest tests/test_factory.py::test_get_provider_fake_returns_fake_provider tests/test_factory.py::test_get_provider_unknown_raises_value_error -v
```

Expected: `2 passed` (the claude import would fail if tested now, but we're not testing it yet)

- [ ] **Step 5: Commit**

```bash
git add app/llm/factory.py tests/test_factory.py
git commit -m "feat: LLM provider factory (fake + claude stub)"
```

---

## Task 8: api/query.py — POST /query (sync JSON, no streaming)

**Files:**
- Create: `backend/app/api/query.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_query_endpoint.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.llm.fake_provider import FakeProvider
from app.sparql.client import SparqlResult


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_sparql_result():
    return SparqlResult(columns=["title"], rows=[{"title": "Αλγόριθμοι"}])


def test_post_query_returns_200_with_correct_shape(client, mock_sparql_result):
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.return_value = mock_sparql_result

        response = client.post(
            "/query",
            json={"question": "Ποια βιβλία;", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "sparql" in body
    assert "PREFIX evdx:" in body["sparql"]
    assert body["columns"] == ["title"]
    assert body["rows"] == [{"title": "Αλγόριθμοι"}]
    assert body["provider"] == "fake"
    assert body["model"] == "fake-v1"
    assert body["retries"] == 0
    assert body["input_tokens"] >= 0
    assert body["output_tokens"] >= 0


def test_post_query_retries_on_invalid_sparql(client, mock_sparql_result):
    """When the first LLM response is invalid SPARQL, the endpoint retries."""
    bad_sparql = "NOT VALID SPARQL !!!"
    good_sparql = (
        "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
        "SELECT ?t WHERE { ?b a evdx:Book ; evdx:title ?t } LIMIT 5"
    )

    call_count = 0

    def fake_generate(system, user, *, max_tokens=1024):
        nonlocal call_count
        from app.llm.base import LLMResponse
        call_count += 1
        return LLMResponse(
            text=bad_sparql if call_count == 1 else good_sparql,
            input_tokens=10,
            output_tokens=5,
        )

    fake = FakeProvider()
    fake.generate = fake_generate

    with (
        patch("app.api.query.get_provider", return_value=fake),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.return_value = mock_sparql_result

        response = client.post(
            "/query",
            json={"question": "test", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["retries"] == 1
    assert body["sparql"] == good_sparql


def test_post_query_returns_502_on_sparql_execution_failure(client):
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.side_effect = RuntimeError("timeout")

        response = client.post(
            "/query",
            json={"question": "test", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 502
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_query_endpoint.py -v
```

Expected: `ImportError` (app.main not created yet — that's OK, we create query.py first, main.py next task)

- [ ] **Step 3: Implement api/query.py**

Create `backend/app/api/query.py`:

```python
"""POST /query — synchronous JSON endpoint.
POST /query/stream — SSE streaming endpoint (added in a later task).

TODO: future — convert to fully async pipeline for higher concurrency.
TODO: future — add auth/rate limiting before any public deployment.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.llm.factory import get_provider
from app.ontology.loader import load_summary
from app.prompts.loader import fill, load
from app.sparql.client import SparqlClient, validate_sparql

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_RETRIES = 2


class QueryRequest(BaseModel):
    question: str
    provider: str = settings.llm_provider
    model: str = settings.llm_model


class QueryResponse(BaseModel):
    sparql: str
    columns: list[str]
    rows: list[dict]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    provider = get_provider(request.provider, request.model)
    ontology = load_summary()
    system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)

    sparql, total_input, total_output, retries = _generate_with_retry(
        provider, system, request.question, ontology
    )

    client = SparqlClient(settings.graphdb_endpoint)
    try:
        result = client.execute(sparql)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return QueryResponse(
        sparql=sparql,
        columns=result.columns,
        rows=result.rows,
        provider=request.provider,
        model=request.model,
        input_tokens=total_input,
        output_tokens=total_output,
        retries=retries,
    )


def _generate_with_retry(provider, system: str, question: str, ontology: str):
    """Call the LLM, validate SPARQL output, retry up to _MAX_RETRIES times.

    TODO: future — extend LLMProvider to support multi-turn conversation for richer retry context.
    """
    retry_template = load("nl-to-sparql-retry", 1)
    total_input = total_output = 0
    sparql = error = ""

    for attempt in range(_MAX_RETRIES + 1):
        current_system = (
            system
            if attempt == 0
            else fill(
                retry_template,
                ontology_summary=ontology,
                failed_sparql=sparql,
                error=error,
            )
        )

        response = provider.generate(current_system, question)
        total_input += response.input_tokens
        total_output += response.output_tokens
        sparql = _clean_sparql(response.text)

        if _is_not_answerable(sparql):
            return sparql, total_input, total_output, attempt

        error = validate_sparql(sparql) or ""
        if not error:
            return sparql, total_input, total_output, attempt

        logger.warning("Invalid SPARQL on attempt %d: %s", attempt + 1, error[:120])

    logger.error("SPARQL still invalid after %d retries: %s", _MAX_RETRIES, error)
    return sparql, total_input, total_output, _MAX_RETRIES


def _clean_sparql(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped the query despite being told not to."""
    text = text.strip()
    m = re.match(r"^```(?:sparql)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def _is_not_answerable(text: str) -> bool:
    """Detect the NOT_ANSWERABLE sentinel defined in the prompt rules."""
    return bool(re.match(r"^#\s*NOT_ANSWERABLE", text.strip()))
```

- [ ] **Step 4: Commit query.py before wiring main.py**

```bash
git add app/api/query.py
git commit -m "feat: POST /query endpoint — sync JSON pipeline with retry"
```

---

## Task 9: app/main.py + smoke test

**Files:**
- Create: `backend/app/main.py`

- [ ] **Step 1: Implement app/main.py**

Create `backend/app/main.py`:

```python
"""FastAPI application entry point.

Run with: uv run fastapi dev app/main.py
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.query import router as query_router
from app.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="evdo-nlq", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
```

- [ ] **Step 2: Run all tests so far**

```bash
uv run pytest -v
```

Expected: all tests from Tasks 2–7 pass. test_query_endpoint.py may still fail because `app.main` was missing — it should now pass too.

Fix any import errors before continuing.

- [ ] **Step 3: Manual smoke test with FakeProvider**

In `.env`, set `LLM_PROVIDER=fake`. Then:

```bash
uv run fastapi dev app/main.py
```

In a second terminal:

```bash
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Ποια βιβλία;", "provider": "fake", "model": "fake-v1"}' | python -m json.tool
```

Expected: JSON with `sparql`, `columns`, `rows` fields. `rows` will be empty (FakeProvider SPARQL hits real GraphDB — if GraphDB is down, you'll get a 502, which is correct behavior).

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: FastAPI entrypoint — CORS, logging, query router"
```

---

## Task 10: Retry prompt file + verify retry path

**Files:**
- Create: `prompts/nl-to-sparql-retry-v1.md`

- [ ] **Step 1: Create the retry prompt**

Create `prompts/nl-to-sparql-retry-v1.md` (at repo root `prompts/`):

```markdown
---
name: nl-to-sparql-retry
version: 1
created: 2026-04-25
author: swtman
notes: Single-turn retry. The failed SPARQL and error are injected into the system prompt.
       The user message (question) is passed unchanged from the original request.
       See ADR-004 for why we chose single-turn over multi-turn retry.
---

# System

You are a SPARQL query generator for the EvdoGraph knowledge graph, which describes textbooks recommended in courses at Greek universities (the Eudoxus system).

Your previous attempt to generate a SPARQL query produced a parse error. Study the error and the failed query below, then output a corrected query.

## Ontology (compact summary)

{ontology_summary}

## Previous attempt (invalid SPARQL)

{failed_sparql}

## Parse error from the previous attempt

{error}

## Rules

1. Output **only the corrected SPARQL query** — no explanation, no Markdown fences, no prose.
2. Use the exact prefixes and URIs from the ontology above. Do NOT invent properties or classes.
3. Prefer `SELECT DISTINCT` over `SELECT` when the question could produce duplicates.
4. Always `LIMIT` your results to 50 unless the user explicitly asks for a count or for "all".
5. For Greek-language string matching, use `CONTAINS(LCASE(?label), LCASE("..."))`.
6. If a property could be under multiple paths, use a property path (`/`, `*`).

# User (template)

{question}

# Notes

## Known limitations of v1

- Single-turn retry: the model sees the error but not a conversational history.
  Multi-turn retry (passing the error as an assistant/user exchange) is planned for v2.
```

- [ ] **Step 2: Verify the retry test from Task 8 passes**

```bash
uv run pytest tests/test_query_endpoint.py::test_post_query_retries_on_invalid_sparql -v
```

Expected: `1 passed`

- [ ] **Step 3: Run full suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
# commit from repo root since the file lives in prompts/
git -C .. add prompts/nl-to-sparql-retry-v1.md
git -C .. commit -m "feat: add nl-to-sparql-retry-v1.md prompt for SPARQL error recovery"
```

---

## Task 11: tests/test_sparql_client.py — additional edge cases

_(test_sparql_client.py was created in Task 6; this task adds a live-marked test)_

**Files:**
- Modify: `backend/tests/test_sparql_client.py`

- [ ] **Step 1: Add a live-marked smoke test at the bottom of test_sparql_client.py**

Append to `backend/tests/test_sparql_client.py`:

```python
@pytest.mark.live
def test_live_execute_returns_results():
    """Requires live GraphDB endpoint. Run with: uv run pytest -m live"""
    from app.config import settings
    client = SparqlClient(settings.graphdb_endpoint)
    result = client.execute(
        "PREFIX evdx: <https://w3id.org/evdoxus#> "
        "SELECT (COUNT(*) AS ?n) WHERE { ?s a evdx:Book } LIMIT 1"
    )
    assert result.columns == ["n"]
    assert len(result.rows) == 1
    count = int(result.rows[0]["n"])
    assert count > 0
```

- [ ] **Step 2: Verify live test is skipped by default**

```bash
uv run pytest tests/test_sparql_client.py -v
```

Expected: `5 passed` (live test skipped because `-m live` was not passed).

- [ ] **Step 3: Commit**

```bash
git add tests/test_sparql_client.py
git commit -m "test: add live SPARQL smoke test (skipped by default)"
```

---

## Task 12: llm/cache.py

**Files:**
- Create: `backend/app/llm/cache.py`
- Test: `backend/tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_cache.py`:

```python
from app.llm.cache import DiskCache


def test_cache_miss_returns_none(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"))
    assert cache.get("system", "user", "model") is None


def test_cache_set_then_get_returns_value(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"))
    cache.set("system", "user", "model", "SELECT * WHERE {}")
    result = cache.get("system", "user", "model")
    assert result == "SELECT * WHERE {}"


def test_cache_different_key_returns_none(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"))
    cache.set("system", "user", "model-a", "value-a")
    assert cache.get("system", "user", "model-b") is None


def test_cache_disabled_never_stores(tmp_path):
    cache = DiskCache(str(tmp_path / "cache"), disabled=True)
    cache.set("s", "u", "m", "value")
    assert cache.get("s", "u", "m") is None


def test_cache_creates_directory_automatically(tmp_path):
    cache_dir = tmp_path / "deep" / "nested" / "cache"
    cache = DiskCache(str(cache_dir))
    cache.set("s", "u", "m", "value")
    assert cache_dir.exists()
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement cache.py**

Create `backend/app/llm/cache.py`:

```python
"""Disk cache for LLM responses, keyed on sha256(system + user + model).

Prevents re-calling the API for identical prompts during development.
Cache directory is gitignored. Disable with LLM_CACHE_DISABLED=1.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DiskCache:
    def __init__(self, cache_dir: str, disabled: bool = False) -> None:
        self._dir = Path(cache_dir)
        self._disabled = disabled
        if not disabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, system: str, user: str, model: str) -> str:
        payload = json.dumps(
            {"system": system, "user": user, "model": model}, ensure_ascii=False
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, system: str, user: str, model: str) -> str | None:
        if self._disabled:
            return None
        path = self._dir / self._key(system, user, model)
        if path.exists():
            logger.debug("Cache hit: %s", path.name[:12])
            return path.read_text(encoding="utf-8")
        return None

    def set(self, system: str, user: str, model: str, value: str) -> None:
        if self._disabled:
            return
        path = self._dir / self._key(system, user, model)
        path.write_text(value, encoding="utf-8")
        logger.debug("Cache write: %s", path.name[:12])
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add app/llm/cache.py tests/test_cache.py
git commit -m "feat: disk LLM response cache (sha256-keyed)"
```

---

## Task 13: llm/claude_provider.py

**Files:**
- Create: `backend/app/llm/claude_provider.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_claude_provider.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from app.llm.base import LLMResponse
from app.llm.cache import DiskCache


def _make_provider(tmp_path, model="claude-haiku-4-5"):
    from app.llm.claude_provider import ClaudeProvider
    cache = DiskCache(str(tmp_path / "cache"))
    return ClaudeProvider(model=model, api_key="test-key", cache=cache)


def _mock_message(text: str, input_tokens: int = 100, output_tokens: int = 50):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    return msg


def test_generate_returns_llm_response(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(provider._client.messages, "create", return_value=_mock_message("SELECT *")):
        result = provider.generate("system", "user")
    assert isinstance(result, LLMResponse)
    assert result.text == "SELECT *"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_generate_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(
        provider._client.messages, "create", return_value=_mock_message("SELECT *")
    ) as mock_create:
        provider.generate("system", "user")
        provider.generate("system", "user")  # second call — should hit cache
    assert mock_create.call_count == 1  # API called only once


def test_generate_does_not_call_api_when_cache_hit(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")
    with patch.object(provider._client.messages, "create") as mock_create:
        result = provider.generate("system", "user")
    mock_create.assert_not_called()
    assert result.text == "CACHED SPARQL"


def test_stream_yields_tokens(tmp_path):
    provider = _make_provider(tmp_path)
    tokens = ["PREFIX", " evdx:", " <...>\n", "SELECT *"]

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_stream_ctx.text_stream = iter(tokens)
    mock_final = MagicMock()
    mock_final.usage.input_tokens = 80
    mock_final.usage.output_tokens = 30
    mock_stream_ctx.get_final_message.return_value = mock_final

    with patch.object(provider._client.messages, "stream", return_value=mock_stream_ctx):
        result = list(provider.stream("system", "user"))

    assert result == tokens
    assert provider.last_input_tokens == 80
    assert provider.last_output_tokens == 30


@pytest.mark.live
def test_live_generate_returns_sparql(tmp_path):
    """Requires ANTHROPIC_API_KEY in .env. Run with: uv run pytest -m live"""
    import os
    from app.llm.claude_provider import ClaudeProvider
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    cache = DiskCache(str(tmp_path / "cache"))
    provider = ClaudeProvider(model="claude-haiku-4-5", api_key=key, cache=cache)
    result = provider.generate("Respond with only: SELECT * WHERE {}", "test")
    assert "SELECT" in result.text
    assert result.input_tokens > 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_claude_provider.py -v -m "not live"
```

Expected: `ImportError`

- [ ] **Step 3: Implement claude_provider.py**

Create `backend/app/llm/claude_provider.py`:

```python
"""Claude (Anthropic) implementation of LLMProvider.

Only this file may import anthropic — all other modules must go through the
LLMProvider protocol to keep the provider abstraction honest.
"""
from __future__ import annotations

import logging
from typing import Iterator

import anthropic

from app.llm.base import LLMProvider, LLMResponse
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class ClaudeProvider:
    """Anthropic Claude implementation. Wraps every call with a disk cache."""

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._cache = cache
        # Set after stream() completes — read by the streaming endpoint for the done event.
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    def generate(
        self, system: str, user: str, *, max_tokens: int = 1024
    ) -> LLMResponse:
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = message.content[0].text
        self._cache.set(system, user, self._model, text)

        logger.info(
            "Claude [%s] input=%d output=%d",
            self._model,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )
        return LLMResponse(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    def stream(
        self, system: str, user: str, *, max_tokens: int = 1024
    ) -> Iterator[str]:
        """Yield raw text tokens from the Claude streaming API.

        After the generator is exhausted, last_input_tokens and last_output_tokens
        are set so callers can include them in the SSE 'done' event.

        TODO: future — run in a thread pool to avoid blocking the async event loop.
        """
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            yield cached
            return

        full_text = ""
        with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for token in stream.text_stream:
                full_text += token
                yield token

        self._cache.set(system, user, self._model, full_text)
        usage = stream.get_final_message().usage
        self.last_input_tokens = usage.input_tokens
        self.last_output_tokens = usage.output_tokens
        logger.info(
            "Claude stream [%s] input=%d output=%d",
            self._model,
            self.last_input_tokens,
            self.last_output_tokens,
        )
```

- [ ] **Step 4: Run to verify tests pass**

```bash
uv run pytest tests/test_claude_provider.py -v -m "not live"
```

Expected: `4 passed`

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -v -m "not live"
```

Expected: all non-live tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/llm/claude_provider.py tests/test_claude_provider.py
git commit -m "feat: ClaudeProvider with generate + stream and disk cache integration"
```

---

## Task 14: api/providers.py + update main.py

**Files:**
- Create: `backend/app/api/providers.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_query_endpoint.py`:

```python
def test_get_providers_returns_list(client):
    response = client.get("/providers")
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    ids = [p["id"] for p in body["providers"]]
    assert "claude" in ids
    assert "fake" in ids
    # Each provider has a non-empty models list
    for p in body["providers"]:
        assert len(p["models"]) > 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_query_endpoint.py::test_get_providers_returns_list -v
```

Expected: `FAILED` (404 — route not mounted yet)

- [ ] **Step 3: Create providers.py**

Create `backend/app/api/providers.py`:

```python
"""GET /providers — returns the list of LLM providers and models available in the UI dropdown."""
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
    ProviderInfo(id="fake", models=["fake-v1"]),
]


@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    return ProvidersResponse(providers=_PROVIDERS)
```

- [ ] **Step 4: Mount the providers router in main.py**

Edit `backend/app/main.py` — add the import and `include_router` call:

```python
"""FastAPI application entry point.

Run with: uv run fastapi dev app/main.py
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.providers import router as providers_router
from app.api.query import router as query_router
from app.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="evdo-nlq", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(providers_router)
```

- [ ] **Step 5: Run to verify it passes**

```bash
uv run pytest tests/test_query_endpoint.py -v
```

Expected: all tests in the file pass including the new providers test.

- [ ] **Step 6: Commit**

```bash
git add app/api/providers.py app/main.py tests/test_query_endpoint.py
git commit -m "feat: GET /providers endpoint + mount in main.py"
```

---

## Task 15: POST /query/stream (SSE)

**Files:**
- Modify: `backend/app/api/query.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_query_endpoint.py`:

```python
def test_post_query_stream_yields_sse_events(client, mock_sparql_result):
    """The streaming endpoint must emit sparql_token, sparql_complete, results, and done events."""
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.return_value = mock_sparql_result

        with client.stream("POST", "/query/stream", json={
            "question": "Ποια βιβλία;", "provider": "fake", "model": "fake-v1"
        }) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            raw = response.read().decode()

    assert "event: sparql_token" in raw
    assert "event: sparql_complete" in raw
    assert "event: results" in raw
    assert "event: done" in raw
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_query_endpoint.py::test_post_query_stream_yields_sse_events -v
```

Expected: `FAILED` (404 — route not added yet)

- [ ] **Step 3: Add the streaming endpoint to api/query.py**

Add the following imports and endpoint to `backend/app/api/query.py` (append after the existing `query` function):

```python
import json
from sse_starlette.sse import EventSourceResponse


@router.post("/query/stream")
async def query_stream(request: QueryRequest) -> EventSourceResponse:
    """SSE streaming endpoint. Emits events:
      sparql_token   — one per LLM output token
      sparql_retry   — when the first attempt fails validation
      sparql_complete — the final (validated) SPARQL string
      results        — JSON execution results from GraphDB
      done           — final metadata (provider, model, tokens, retries)
      error          — on any unrecoverable failure

    NOTE: provider.stream() is a sync iterator called inside an async generator.
    This blocks the event loop per token — acceptable at thesis demo concurrency.
    TODO: future — run provider.stream() in a thread pool (asyncio.to_thread).
    TODO: future — revisit transport when building the React frontend:
          browser EventSource only supports GET; use fetch + ReadableStream (POST).
    """

    async def event_generator():
        try:
            provider = get_provider(request.provider, request.model)
            ontology = load_summary()
            system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)

            # Phase 1: stream SPARQL tokens
            full_sparql = ""
            for token in provider.stream(system, request.question):
                full_sparql += token
                yield {"event": "sparql_token", "data": token}

            total_input = getattr(provider, "last_input_tokens", 0)
            total_output = getattr(provider, "last_output_tokens", 0)
            full_sparql = _clean_sparql(full_sparql)

            # Phase 2: validate + retry (non-streaming retries)
            retries = 0
            retry_template = load("nl-to-sparql-retry", 1)
            error = validate_sparql(full_sparql) or ""

            while error and retries < _MAX_RETRIES:
                retries += 1
                yield {
                    "event": "sparql_retry",
                    "data": json.dumps({"attempt": retries, "error": error}),
                }
                retry_system = fill(
                    retry_template,
                    ontology_summary=ontology,
                    failed_sparql=full_sparql,
                    error=error,
                )
                response_obj = provider.generate(retry_system, request.question)
                full_sparql = _clean_sparql(response_obj.text)
                total_input += response_obj.input_tokens
                total_output += response_obj.output_tokens
                error = validate_sparql(full_sparql) or ""

            yield {"event": "sparql_complete", "data": full_sparql}

            # Phase 3: execute against GraphDB
            client = SparqlClient(settings.graphdb_endpoint)
            result = client.execute(full_sparql)
            yield {
                "event": "results",
                "data": json.dumps({"columns": result.columns, "rows": result.rows}),
            }

            # Phase 4: done
            yield {
                "event": "done",
                "data": json.dumps({
                    "provider": request.provider,
                    "model": request.model,
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                    "retries": retries,
                }),
            }

        except Exception as exc:
            logger.error("Stream error: %s", exc)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_query_endpoint.py -v
```

Expected: all tests pass including the new SSE test.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -v -m "not live"
```

Expected: all non-live tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/api/query.py tests/test_query_endpoint.py
git commit -m "feat: POST /query/stream SSE endpoint with token streaming and retry"
```

---

## Task 16: Update CLAUDE.md and PROGRESS.md

**Files:**
- Modify: `backend/CLAUDE.md`
- Modify: `notes/PROGRESS.md`

- [ ] **Step 1: Add streaming and per-request provider docs to backend/CLAUDE.md**

In `backend/CLAUDE.md`, add a new section after the existing layout table:

```markdown
## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/query` | Sync JSON — full response after pipeline completes |
| `POST` | `/query/stream` | SSE — streams SPARQL tokens then results |
| `GET` | `/providers` | Static list of available providers + models |

`POST /query` and `POST /query/stream` both accept:
```json
{"question": "...", "provider": "claude", "model": "claude-haiku-4-5"}
```

**Frontend SSE note:** `/query/stream` must be called with `fetch + ReadableStream`
(not `EventSource`) because EventSource only supports GET.
Revisit when building the React query hook.
```

- [ ] **Step 2: Append a session entry to notes/PROGRESS.md**

Append to `notes/PROGRESS.md`:

```markdown
## 2026-04-25 — Backend pipeline implemented

### Done
- Spec + ADR-004 written and approved.
- Full backend pipeline: config, LLMProvider protocol, FakeProvider, ClaudeProvider (generate + stream), DiskCache, PromptLoader, OntologyLoader (static file), SparqlClient (validate + execute), ProviderFactory.
- POST /query (sync JSON) and POST /query/stream (SSE with retry) implemented and tested.
- GET /providers endpoint (static list for UI dropdown).
- nl-to-sparql-retry-v1.md prompt created.
- prompts/ontology-summary.md created (compact schema for prompt injection).
- All non-live tests pass.

### Next
1. Run live tests against real GraphDB: `uv run pytest -m live`
2. Run live tests against Claude Haiku: `uv run pytest -m live` (requires ANTHROPIC_API_KEY in .env)
3. Start the frontend — React + Vite scaffold, POST /query/stream consumer.
4. Build the query hook with `fetch + ReadableStream` for SSE (see TODO in query.py).

### Blockers / notes
- Internship starts 2026-05-18 — MVP frontend should be stable before then.
- SSE transport: frontend must use `fetch + ReadableStream`, not EventSource (GET-only).
```

- [ ] **Step 3: Run lint and type check**

```bash
uv run ruff check .
uv run ruff format --check .
```

Fix any issues, then:

- [ ] **Step 4: Final full test run**

```bash
uv run pytest -v -m "not live"
```

Expected: all non-live tests pass with no warnings.

- [ ] **Step 5: Final commit**

```bash
git add app/main.py backend/CLAUDE.md
git -C .. add backend/CLAUDE.md notes/PROGRESS.md
git -C .. commit -m "docs: update backend CLAUDE.md and PROGRESS.md after pipeline implementation"
```

---

## Self-review checklist

**Spec coverage:**
- [x] All files from spec section 2 have a creating task
- [x] Pipeline flow (spec section 3) — all 4 phases + retry covered in Tasks 8, 10, 15
- [x] All API schemas (spec section 5) defined in Task 8 / Task 14
- [x] All SSE event types emitted in Task 15
- [x] All prompt files (spec section 6) created in Tasks 5, 10
- [x] All config keys (spec section 7) in Task 2
- [x] All test files (spec section 8) in Tasks 5, 6, 11, 12, 13
- [x] Deferred items noted with TODO in Task 8 / Task 15

**Type consistency:**
- `LLMResponse(text, input_tokens, output_tokens)` — defined Task 3, used Tasks 4, 13, 14
- `SparqlResult(columns, rows)` — defined Task 6, used Tasks 8, 14
- `validate_sparql(query) -> str | None` — defined Task 6, used Tasks 8, 15
- `get_provider(name, model) -> LLMProvider` — defined Task 7, used Tasks 8, 15
- `load(name, version) -> str` / `fill(template, **kwargs) -> str` — defined Task 5, used Tasks 8, 15
- `load_summary() -> str` — defined Task 5, used Tasks 8, 15
- `QueryRequest` / `QueryResponse` — defined Task 8, tested Task 8
- `ProviderInfo` / `ProvidersResponse` — defined Task 14, tested Task 14

**No placeholders:** Verified — no TBD/TODO in step content (only annotated TODO comments in code are intentional).
