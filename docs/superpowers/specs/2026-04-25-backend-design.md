# Backend Design Spec — NLQ Pipeline
**Date:** 2026-04-25  
**Status:** Approved  
**Author:** @swtman

---

## 1. Overview

Single FastAPI service (Python 3.12, sync). Receives a natural-language question and an LLM provider choice from the frontend, generates SPARQL via an LLM, executes it against EvdoGraph's GraphDB endpoint, and returns structured results. The primary endpoint streams the SPARQL generation token-by-token over SSE so the user sees the query being written in real time.

---

## 2. File layout

```
backend/
├── app/
│   ├── main.py                    FastAPI app, CORS, lifespan
│   ├── api/
│   │   ├── query.py               POST /query (JSON), POST /query/stream (SSE)
│   │   └── providers.py           GET /providers
│   ├── llm/
│   │   ├── base.py                LLMProvider protocol, LLMResponse
│   │   ├── claude_provider.py     Anthropic SDK — sync + real streaming
│   │   ├── fake_provider.py       Canned SPARQL, char-by-char fake stream
│   │   ├── factory.py             get_provider(name, model) → LLMProvider
│   │   └── cache.py               Disk cache keyed on sha256(system+user+model)
│   ├── sparql/
│   │   └── client.py              execute(query) → SparqlResult; validate(query) → str | None
│   ├── ontology/
│   │   └── loader.py              load_summary() → str; module-level cache
│   ├── prompts/
│   │   └── loader.py              load(name, version) → str; fill(**kwargs) → str
│   └── config.py                  Pydantic Settings (env-backed)
├── tests/
│   ├── conftest.py
│   ├── test_query_endpoint.py
│   ├── test_sparql_client.py
│   ├── test_prompt_loader.py
│   └── test_cache.py
└── pyproject.toml
```

---

## 3. Pipeline flow

```
POST /query/stream
  1. ProviderFactory.get(request.provider, request.model)
  2. ontology_loader.load_summary()          — module cache, one file read per process
  3. prompt_loader.load("nl-to-sparql", 1)   — fill {ontology_summary}, {question}
  4. provider.stream(system, user)
       → SSE: sparql_token  (one per token)
  5. sparql_client.validate(full_sparql)
       → if invalid and retries < 2:
           prompt_loader.load("nl-to-sparql-retry", 1)   — fill {failed_sparql}, {error}
           provider.generate(retry_system, user)
           → SSE: sparql_retry  {attempt, error}
  6. sparql_client.execute(full_sparql)
       → SSE: results  {columns, rows}
  7. SSE: done  {provider, model, input_tokens, output_tokens, retries}
  8. SSE: error  {message}  — on any unrecoverable failure

POST /query   — same logic, collects all SSE events, returns single QueryResponse JSON
GET /providers — returns static provider+model list for the UI dropdown
```

---

## 4. Module contracts

### `llm/base.py`
```python
class LLMProvider(Protocol):
    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...
    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]: ...

@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
```

### `sparql/client.py`
```python
@dataclass
class SparqlResult:
    columns: list[str]
    rows: list[dict]

class SparqlClient:
    def execute(self, query: str) -> SparqlResult: ...
    def validate(self, query: str) -> str | None: ...   # None = valid
```

### `prompts/loader.py`
```python
def load(name: str, version: int) -> str: ...     # reads prompts/{name}-v{version}.md
def fill(template: str, **kwargs: str) -> str: ... # str.format_map
```

### `ontology/loader.py`
```python
def load_summary() -> str: ...   # reads prompts/ontology-summary.md; cached after first call
```

### `llm/factory.py`
```python
def get_provider(name: str, model: str) -> LLMProvider: ...
# raises ValueError on unknown name
```

---

## 5. API schemas

### Input
```python
class QueryRequest(BaseModel):
    question: str
    provider: str = "claude"
    model: str = "claude-haiku-4-5"
```

### POST /query output
```python
class QueryResponse(BaseModel):
    sparql: str
    columns: list[str]
    rows: list[dict]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int
```

### SSE event types (POST /query/stream)
| Event | Data |
|---|---|
| `sparql_token` | `"<token string>"` |
| `sparql_retry` | `{"attempt": int, "error": str}` |
| `sparql_complete` | `"<full sparql string>"` |
| `results` | `{"columns": [...], "rows": [...]}` |
| `done` | `{"provider": str, "model": str, "input_tokens": int, "output_tokens": int, "retries": int}` |
| `error` | `{"message": str}` |

### GET /providers output
```python
class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]

class ProviderInfo(BaseModel):
    id: str
    models: list[str]
```

---

## 6. Prompt files

| File | Slots |
|---|---|
| `prompts/nl-to-sparql-v1.md` | `{ontology_summary}`, `{question}` |
| `prompts/nl-to-sparql-retry-v1.md` | `{ontology_summary}`, `{question}`, `{failed_sparql}`, `{error}` |
| `prompts/ontology-summary.md` | Static compact schema; read by `ontology/loader.py` |

---

## 7. Config (`.env` keys)

| Key | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `claude` | `claude` \| `fake` |
| `LLM_MODEL` | `claude-haiku-4-5` | Overridden per-request from UI |
| `ANTHROPIC_API_KEY` | — | Required when provider=claude |
| `GRAPHDB_ENDPOINT` | `http://lod.csd.auth.gr:7200/repositories/Evdoxus` | Read-only |
| `LLM_CACHE_DIR` | `.llm_cache` | Gitignored |
| `LLM_CACHE_DISABLED` | `0` | Set to `1` to bypass |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS |
| `LOG_LEVEL` | `INFO` | |

---

## 8. Test surface

| File | Covers |
|---|---|
| `test_query_endpoint.py` | POST /query round-trip with FakeProvider + mock SparqlClient |
| `test_sparql_client.py` | Golden SPARQL: known query → expected result shape |
| `test_prompt_loader.py` | Template loading + slot filling |
| `test_cache.py` | Cache hit / miss / disabled flag |
| Live (`@pytest.mark.live`) | Skipped by default; require real API keys + endpoint |

---

## 9. Deferred (TODO: future in code)

- Full async pipeline (sync is fine at demo concurrency)
- Multi-turn retry (extend protocol to `messages: list`)
- Auth / rate limiting (localhost-only for thesis evaluation)
- OpenAI / Ollama provider implementations
- Frontend SSE transport: uses `POST + fetch/ReadableStream` — **revisit when building the React query hook** (browser `EventSource` only supports GET)
