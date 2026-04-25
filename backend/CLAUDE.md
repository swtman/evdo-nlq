# backend/ — FastAPI service

Python backend. Receives a natural-language question from the frontend, uses an LLM to generate SPARQL, executes it against EvdoGraph's GraphDB endpoint, and returns results.

## Layout

```
backend/
├── app/
│   ├── main.py                    FastAPI entrypoint (creates app, mounts routes, CORS)
│   ├── api/
│   │   └── query.py               POST /query endpoint
│   ├── llm/
│   │   ├── base.py                LLMProvider protocol + response dataclass
│   │   ├── claude_provider.py     Anthropic implementation
│   │   ├── fake_provider.py       For tests and frontend dev (no network)
│   │   └── cache.py               Disk cache keyed on prompt hash
│   ├── sparql/
│   │   └── client.py              SPARQLWrapper-based GraphDB client
│   ├── ontology/
│   │   └── loader.py              Loads + summarizes the EvdoGraph ontology
│   ├── prompts/
│   │   └── loader.py              Reads versioned prompts from ../prompts/
│   └── config.py                  Pydantic settings (env-backed)
├── tests/
│   └── test_*.py
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
uv run pytest                      # all tests
uv run pytest -k "not live"        # skip live-API tests (default)
uv run pytest -m live              # only live-API tests (costs tokens!)
uv run ruff check .                # lint
uv run ruff format .               # format
uv run mypy app                    # type-check (optional but nice)
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
```

Swap providers by changing `LLM_PROVIDER` in `.env`. Never `import anthropic` outside `claude_provider.py`. This keeps the thesis's "provider comparison" chapter honest and makes tests cheap.

## Token-saving rules

- **Default model:** `claude-haiku-4-5`. Configurable via `LLM_MODEL` env var.
- **Cache everywhere:** `ClaudeProvider` wraps every call with a disk cache keyed on `sha256(system + user + model)`. Cache dir: `backend/.llm_cache/`. Gitignored.
- **Kill switch:** if `LLM_PROVIDER=fake`, use `FakeProvider` which returns canned SPARQL. Use this for frontend development and unit tests.
- **Usage logging:** every real call logs `input_tokens` and `output_tokens` at INFO level. Grep the logs to see what's costing you.
- **Ontology is huge** — do not send the full ontology as context on every call. `ontology/loader.py` should produce a compact schema summary (classes + key properties + a few example triples) and cache it in memory on startup.

## Secrets

Never commit `.env`. Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=claude      # or fake, openai, ollama
LLM_MODEL=claude-haiku-4-5
GRAPHDB_ENDPOINT=http://lod.csd.auth.gr:7200/repositories/Evdoxus
GRAPHDB_READONLY=true
```

## SPARQL client

- Use `SPARQLWrapper` for the HTTP client.
- Default format: JSON.
- Always wrap executions in try/except — the endpoint can time out or return malformed SPARQL errors.
- If the LLM returns invalid SPARQL, we want to surface the parse error to the user AND feed it back to the LLM in a retry prompt (bounded — max 2 retries).

## Tests

- Use `FakeProvider` for anything that isn't explicitly a live-API test.
- Mark live tests with `@pytest.mark.live` and skip them by default in CI.
- Golden-SPARQL tests: given canned LLM output, verify our SPARQL client produces expected results. These don't need live calls.

## What NOT to do

- Don't bypass the `LLMProvider` abstraction.
- Don't inline prompt strings in Python — load from `../prompts/*.md`.
- Don't write SPARQL parsers from scratch; use `rdflib.plugins.sparql.parser.parseQuery` for validation.
- Don't commit anything under `.llm_cache/` — it often contains real model outputs you may not want to share.
