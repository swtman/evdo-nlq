# backend/ — FastAPI service

Python backend. Receives a natural-language question from the frontend, uses an LLM to generate SPARQL, executes it against EvdoGraph's GraphDB endpoint, and returns results.

## Layout

```
backend/
├── app/
│   ├── main.py                    FastAPI entrypoint (creates app, mounts routes, CORS)
│   ├── api/
│   │   ├── query.py               POST /query (sync JSON) + POST /query/stream (SSE)
│   │   └── providers.py           GET /providers — static provider+model list for UI
│   ├── llm/
│   │   ├── base.py                LLMProvider protocol (generate + stream) + LLMResponse
│   │   ├── claude_provider.py     Anthropic implementation — only file that imports anthropic
│   │   ├── fake_provider.py       Canned SPARQL, char-by-char stream; for tests + frontend dev
│   │   ├── factory.py             get_provider(name, model) → LLMProvider
│   │   └── cache.py               Disk cache keyed on sha256(system+user+model)
│   ├── sparql/
│   │   └── client.py              validate_sparql() (rdflib) + SparqlClient.execute() (SPARQLWrapper)
│   ├── ontology/
│   │   └── loader.py              load_summary() — reads prompts/ontology-summary.md, module-level cache
│   ├── prompts/
│   │   └── loader.py              load(name, version) + fill(**kwargs) — reads from top-level prompts/
│   └── config.py                  Pydantic Settings (env-backed via .env)
├── tests/
│   ├── test_cache.py
│   ├── test_claude_provider.py
│   ├── test_config.py
│   ├── test_factory.py
│   ├── test_fake_provider.py
│   ├── test_llm_base.py
│   ├── test_prompt_loader.py
│   ├── test_query_endpoint.py
│   └── test_sparql_client.py
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

**Frontend SSE note:** `/query/stream` must be called with `fetch + ReadableStream` (not `EventSource`) because `EventSource` only supports GET. Revisit when building the React query hook.

## Commands

```bash
uv sync                            # install deps
uv run fastapi dev app/main.py     # hot-reload dev server on :8000
uv run pytest -v -m "not live"     # all non-live tests (default — no API keys needed)
uv run pytest -m live              # only live-API tests (costs tokens! needs .env filled)
uv run ruff check .                # lint
uv run ruff format .               # format
uv run mypy app                    # type-check
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
    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]: ...
```

- `generate` is used by `POST /query` (sync) and by the retry loop inside `POST /query/stream`.
- `stream` is used by the first SPARQL generation attempt in `POST /query/stream` — yields tokens live to the SSE client.
- Provider is selected **per request** via `QueryRequest.provider` + `QueryRequest.model`, not just at startup.
- Swap the default by changing `LLM_PROVIDER` / `LLM_MODEL` in `.env`.
- Never `import anthropic` outside `claude_provider.py`. This keeps the thesis's "provider comparison" chapter honest and makes tests cheap.

## Token-saving rules

- **Default model:** `claude-haiku-4-5`. Configurable via `LLM_MODEL` env var.
- **Cache everywhere:** `ClaudeProvider` wraps every call with a disk cache keyed on `sha256(system + user + model)`. Cache dir: `backend/.llm_cache/`. Gitignored.
- **Kill switch:** if `LLM_PROVIDER=fake`, use `FakeProvider` which returns canned SPARQL. Use this for frontend development and unit tests.
- **Usage logging:** every real call logs `input_tokens` and `output_tokens` at INFO level. Grep the logs to see what's costing you.
- **Ontology:** `ontology/loader.py` reads `prompts/ontology-summary.md` (a hand-curated compact schema summary) once at first call and caches it in a module-level variable. No SPARQL at startup. The ontology does not change, so static file is correct.

## Secrets

Never commit `.env`. Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=claude         # or fake (no API key needed)
LLM_MODEL=claude-haiku-4-5
GRAPHDB_ENDPOINT=http://lod.csd.auth.gr:7200/repositories/Evdoxus
LLM_CACHE_DIR=.llm_cache
LLM_CACHE_DISABLED=0        # set to 1 to force fresh calls
FRONTEND_ORIGIN=http://localhost:5173
LOG_LEVEL=INFO
```

## SPARQL client

- `validate_sparql(query)` uses `rdflib.plugins.sparql.parser.parseQuery` — offline, no network, fast.
- `SparqlClient.execute(query)` uses `SPARQLWrapper`, JSON format, wrapped in try/except raising `RuntimeError`.
- Retry loop in `_generate_with_retry`: on invalid SPARQL, the error string is injected into the `nl-to-sparql-retry-v1.md` prompt and a new `generate()` call is made. Max 2 retries.
- `NOT_ANSWERABLE` sentinel (`# NOT_ANSWERABLE: ...`) is detected before validation and short-circuits execution in both `/query` and `/query/stream`.

## Tests

- Use `FakeProvider` for anything that isn't explicitly a live-API test.
- Mark live tests with `@pytest.mark.live` and skip them by default: `uv run pytest -m "not live"`.
- Live tests that do hit real endpoints: `test_live_execute_returns_results` (GraphDB) and `test_live_generate_returns_sparql` (Claude). Run with `uv run pytest -m live`.
- Endpoint tests (`test_query_endpoint.py`) patch `get_provider` and `SparqlClient` — they never hit real APIs.
- 34 non-live tests, 2 live tests as of backend completion.

## What NOT to do

- Don't bypass the `LLMProvider` abstraction — use `factory.get_provider()`, not direct imports.
- Don't inline prompt strings in Python — use `prompts.loader.load(name, version)` to read from `prompts/*.md`.
- Don't write SPARQL parsers from scratch — use `rdflib.plugins.sparql.parser.parseQuery` via `validate_sparql()`.
- Don't commit anything under `.llm_cache/` — it contains real model outputs.
- Don't `import anthropic` anywhere except `claude_provider.py`.
