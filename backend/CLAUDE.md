# backend/ — FastAPI service

Python backend. Receives a natural-language question from the frontend, uses an LLM to generate SPARQL, executes it against EvdoGraph's GraphDB endpoint, and returns results via SSE.

## Layout

```
backend/
├── app/
│   ├── main.py                    FastAPI entrypoint (creates app, mounts routes, CORS)
│   ├── api/
│   │   ├── query.py               Thin route handlers only — delegates to QueryPipeline
│   │   └── providers.py           GET /providers — static provider+model list for UI
│   ├── pipeline/
│   │   └── query_pipeline.py      QueryPipeline: all business logic (retry, events, execution)
│   ├── llm/
│   │   ├── base.py                LLMProvider protocol + LLMResponse + StreamResult
│   │   ├── claude_provider.py     Anthropic implementation — only file that imports anthropic
│   │   ├── gemini_provider.py     Google Gemini implementation — only file that imports google-genai
│   │   ├── fake_provider.py       Canned SPARQL, char-by-char stream; for tests + UI dev
│   │   ├── factory.py             get_provider(name, model) → LLMProvider
│   │   └── cache.py               DiskCache keyed on sha256(system+user+model)
│   ├── sparql/
│   │   └── client.py              validate_sparql() (rdflib) + SparqlClient.execute() (SPARQLWrapper)
│   ├── ontology/
│   │   └── loader.py              load_summary() — reads prompts/ontology-summary.md, module-level cache
│   ├── prompts/
│   │   └── loader.py              load(name, version) + fill(**kwargs) — module-level cache
│   └── config.py                  Pydantic Settings (env-backed via .env)
├── tests/
│   ├── test_cache.py
│   ├── test_claude_provider.py    includes @pytest.mark.live test (needs ANTHROPIC_API_KEY)
│   ├── test_config.py
│   ├── test_factory.py
│   ├── test_fake_provider.py
│   ├── test_gemini_provider.py    includes @pytest.mark.live test (needs GEMINI_API_KEY)
│   ├── test_llm_base.py
│   ├── test_prompt_loader.py
│   ├── test_query_endpoint.py
│   ├── test_query_pipeline.py     QueryPipeline unit tests (sync + async, no HTTP)
│   └── test_sparql_client.py     includes @pytest.mark.live test (needs live GraphDB)
├── pyproject.toml
├── .env.example
└── CLAUDE.md  ← you are here
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/query` | Sync JSON — full pipeline response after completion |
| `POST` | `/query/stream` | SSE — streams SPARQL tokens then results |
| `GET` | `/providers` | Static list of available providers + models |

Both `/query` and `/query/stream` accept:
```json
{"question": "...", "provider": "claude", "model": "claude-haiku-4-5"}
```

**SSE transport note:** `/query/stream` must be called with `fetch + ReadableStream` (not `EventSource`) because `EventSource` only supports GET. `sse_starlette` emits `\r\n` line endings and `\r\n\r\n` event separators — the frontend SSE parser normalizes these to `\n` before splitting.

## Commands

```powershell
uv sync                              # install deps
uv run fastapi dev app/main.py       # hot-reload dev server on :8000
uv run pytest -v -m "not live"       # all non-live tests (default — no API keys needed, 40 tests)
uv run pytest -m live                # live-API tests (3 tests, costs tokens — see below)
uv run ruff check .                  # lint
uv run ruff format .                 # format
uv run mypy app                      # type-check
```

### Running live tests

Pytest does **not** auto-load `.env`. Export the relevant key into the shell first:

```powershell
# Claude live test
$env:ANTHROPIC_API_KEY = (Get-Content .env | Select-String '^ANTHROPIC_API_KEY=' | ForEach-Object { ($_ -split '=',2)[1] })
uv run pytest tests/test_claude_provider.py -m live -v

# Gemini live test
$env:GEMINI_API_KEY = (Get-Content .env | Select-String '^GEMINI_API_KEY=' | ForEach-Object { ($_ -split '=',2)[1] })
uv run pytest tests/test_gemini_provider.py -m live -v

# GraphDB live test (no API key needed, just network access)
uv run pytest tests/test_sparql_client.py -m live -v

# All live tests at once
$env:ANTHROPIC_API_KEY = ...
uv run pytest -m live -v
```

## Code style

- **Python 3.12**, type hints everywhere.
- Line length 100, `ruff` defaults.
- Prefer Pydantic models for API request/response schemas.
- Logging via `logging.getLogger(__name__)`, never `print` in production paths.

## The LLM abstraction (important)

All LLM calls go through `app/llm/base.py`:

```python
class LLMProvider(Protocol):
    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...
    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult: ...
```

`StreamResult` bundles the token iterator with usage metadata:
```python
@dataclass
class StreamResult:
    tokens: Iterator[str]   # exhaust this first
    input_tokens: int       # populated after tokens is exhausted
    output_tokens: int      # populated after tokens is exhausted
```

- `generate` is used by the sync path and the retry loop in the streaming path.
- `stream` returns a `StreamResult`; the pipeline iterates `result.tokens` then reads `result.input_tokens` / `result.output_tokens`.
- Provider is selected **per request** via `QueryRequest.provider` + `QueryRequest.model`.
- Swap the default by changing `LLM_PROVIDER` / `LLM_MODEL` in `.env`.
- Never `import anthropic` outside `claude_provider.py`, never `import google.generativeai` outside `gemini_provider.py`.

## Pipeline architecture

All business logic lives in `app/pipeline/query_pipeline.py`. Route handlers in `app/api/query.py` are thin wrappers that call `QueryPipeline.run()` or `QueryPipeline.stream_events()`.

`QueryPipeline` is constructed per-request via `_make_pipeline()` in `query.py`, which injects both the `LLMProvider` (from `factory.get_provider`) and the `SparqlClient`.

`stream_events()` is an `async` generator. Phase 1 (token streaming) runs each `next()` call in a thread pool (`asyncio.get_running_loop().run_in_executor`) to avoid blocking the event loop. Phases 2–4 use sync calls (acceptable at thesis-demo concurrency).

## Token-saving rules

- **Default model:** `claude-haiku-4-5`. Configurable via `LLM_MODEL` env var.
- **Cache everywhere:** both `ClaudeProvider` and `GeminiProvider` wrap calls with `DiskCache` keyed on `sha256(system + user + model)`. Cache dir: `backend/.llm_cache/` (gitignored).
- **Kill switch:** `LLM_PROVIDER=fake` uses `FakeProvider` (canned SPARQL, no network). Use for UI dev and unit tests.
- **Usage logging:** every real call logs `input_tokens` and `output_tokens` at INFO level.
- **Ontology:** `ontology/loader.py` reads `prompts/ontology-summary.md` once at first call and caches it module-level. ~400 tokens, loaded per request.

## Secrets

Never commit `.env`. Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...          # optional — only needed for gemini provider
LLM_PROVIDER=claude             # claude | gemini | fake
LLM_MODEL=claude-haiku-4-5
GRAPHDB_ENDPOINT=http://lod.csd.auth.gr:7200/repositories/Evdoxus
LLM_CACHE_DIR=.llm_cache
LLM_CACHE_DISABLED=0            # set to 1 to force fresh LLM calls
FRONTEND_ORIGIN=http://localhost:5173
LOG_LEVEL=INFO
```

## SPARQL pipeline (query_pipeline.py)

Business logic lives in `QueryPipeline.stream_events()` (streaming) and `QueryPipeline.run()` (sync). The route handlers only map typed events to SSE dicts.

1. **Stream phase** — `provider.stream()` returns `StreamResult`; each token from `result.tokens` is yielded as `TokenEvent`.
2. **Clean** — `_clean_sparql()` strips markdown code fences.
3. **NOT_ANSWERABLE check** — if the LLM returned `# NOT_ANSWERABLE: ...`, yield `CompleteEvent` + `DoneEvent` and return without hitting GraphDB.
4. **Validate + retry** — `validate_sparql()` via rdflib (offline). On failure, inject error into the retry prompt and call `provider.generate()` up to `_MAX_RETRIES` (2) times. Each failure emits a `RetryEvent`.
5. **Execute** — `SparqlClient.execute()` via SPARQLWrapper against GraphDB → `ResultsEvent`.
6. **Done** — `DoneEvent` carries provider, model, token counts, retry count.

**SELECT-only constraint:** `SparqlClient.execute()` assumes the SPARQL SELECT JSON response shape (`head.vars` + `results.bindings`). CONSTRUCT and ASK queries return different formats and are not handled — they would silently return an empty result. The LLM prompt instructs the model to only generate SELECT queries; this is a convention-level constraint, not enforced in code.

## Tests

- Use `FakeProvider` for anything that isn't explicitly a live-API test.
- Mark live tests with `@pytest.mark.live` and skip them by default.
- **50 non-live tests**, **3 live tests**:
  - `test_claude_provider.py::test_live_generate_returns_sparql` — hits Anthropic API
  - `test_gemini_provider.py::test_live_generate_returns_sparql` — hits Google API
  - `test_sparql_client.py::test_live_execute_returns_results` — hits GraphDB
- Pipeline tests (`test_query_pipeline.py`) test `QueryPipeline` directly without HTTP.
- Endpoint tests (`test_query_endpoint.py`) patch `get_provider` and `SparqlClient` — never hit real APIs.

## What NOT to do

- Don't bypass the `LLMProvider` abstraction — use `factory.get_provider()`, not direct imports.
- Don't inline prompt strings in Python — use `prompts.loader.load(name, version)`.
- Don't write SPARQL parsers from scratch — use `validate_sparql()` which wraps rdflib.
- Don't commit anything under `.llm_cache/` — it contains real model outputs.
- Don't `import anthropic` anywhere except `claude_provider.py`; don't `import google` anywhere except `gemini_provider.py`.
