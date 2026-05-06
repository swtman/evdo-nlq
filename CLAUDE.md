# evdograph-nlq — Natural Language Queries on EvdoGraph

> Thesis project (AUTh CSD, 2026): users ask questions about Greek university textbooks in plain language; an LLM turns each question into SPARQL, it runs against EvdoGraph, and results are rendered in a web UI.

## Pipeline in one picture

```
User (NL, Greek/English)
  → React UI  (http://localhost:5173)
  → FastAPI POST /query/stream  (SSE, streams SPARQL tokens live)
  → LLMProvider (Claude / Gemini / Fake)  ←  ontology summary (prompts/ontology-summary.md)
                                          ←  few-shot examples (prompts/examples.yaml, k=6)
  → SPARQL string  →  rdflib validation  →  retry up to 2× if invalid
  → GraphDB endpoint (http://lod.csd.auth.gr:7200/repositories/Evdoxus)
  → results (JSON)
  → React UI (collapsible SPARQL panel + results table)

Provider and model are selected per-request from the UI dropdown (GET /providers).
Active prompt: nl-to-sparql-v2 (static few-shot, 6 examples injected into {few_shot_block}).
```

## Stack at a glance

- **Backend:** Python 3.12, FastAPI, `rdflib`, `SPARQLWrapper`, `anthropic` SDK, `google-genai` SDK, `sse-starlette`, `pytest`, `ruff`. **Status: complete.**
- **Frontend:** React 18 + Vite + TypeScript, plain CSS. **Status: MVP complete (2026-05-01).**
- **Triple store:** remote GraphDB at `http://lod.csd.auth.gr:7200/repositories/Evdoxus` — EvdoGraph repository. We do not self-host.
- **LLM:** pluggable (`LLMProvider` protocol). Implemented: `claude` (Anthropic), `gemini` (Google), `fake` (no-network, for tests). Default query model: `claude-haiku-4-5`.
- **Package managers:** `uv` for Python, `pnpm` for Node.

## Repository map

| Path | What's there |
|------|--------------|
| `backend/` | FastAPI service — fully implemented (64 non-live tests + 3 live tests) |
| `frontend/` | React + Vite SPA — MVP complete; light/dark theme, GraphDB indicator, error UX |
| `thesis/` | Thesis document (Greek), chapter drafts, figures, cited PDFs |
| `decisions/` | Architecture Decision Records (ADRs 001–006) — read these to understand *why* code is shaped this way |
| `prompts/` | Versioned LLM prompt templates: `nl-to-sparql-v2.md` (active), `nl-to-sparql-v1.md` (archived), `nl-to-sparql-retry-v1.md`, `ontology-summary.md`, `examples.yaml` (21 gold few-shot examples) |
| `notes/` | Running notes: `PROGRESS.md` (session log), `ONTOLOGY-NOTES.md` (EvdoGraph schema notes) |
| `notes/eval-runs/` | Eval harness Markdown reports (auto-named by date/version/provider) |
| `scripts/` | Standalone helpers (SPARQL smoke test, ontology introspection) |
| `docs/` | Design specs and implementation plans (`docs/superpowers/`) |

## Language conventions

- Thesis text: **Greek**.
- Code, comments, commit messages, CLAUDE.md, README, ADRs: **English**.
- UI: **Greek primary**, English toggle a stretch goal.
- Ontology labels and data are Greek — plan for Greek tokenization in prompts and examples.

## Always do this
- Always document the code.
- Before editing code in a subfolder, read that subfolder's `CLAUDE.md`.
- When making a real technical choice (library, design pattern, schema), write an ADR in `decisions/` immediately.
- At the end of each session, append to `notes/PROGRESS.md`: *done / next / blockers*.
- Keep LLM prompts in `prompts/`, referenced by version (`nl-to-sparql@v1`), never inlined.
- Before commit: `uv run pytest` (backend) and `pnpm typecheck` (frontend).

## Don't do this

- Don't commit `.env` or API keys.
- Don't bypass the `LLMProvider` abstraction — swap providers by config, not by `if` branches.
- Don't call live LLMs in unit tests. Use the `FakeProvider`.
- Don't inline SPARQL strings in frontend code — the frontend only shows what the backend returns.

## Cost awareness (this is a student project on a tight token budget)

- Default model for code development: **`claude-sonnet-4-6`**. Switch to `claude-opus-4-7` for planning and more complex tasks.
- Default model for generating SPARQL queries: **`claude-haiku-4-5`**. Switch to `claude-sonnet-4-6` only for side-by-side comparisons or when Haiku clearly underperforms.
- **Cache all LLM responses on disk during dev** — same prompt hashes to the same response. Cache lives under `backend/.llm_cache/` (gitignored).
- **Fake provider for tests and UI iteration.** Real API calls only when deliberately testing the pipeline.
- **Print token usage** for every real call (`response.usage.input_tokens` / `output_tokens`) — catch prompt bloat early.
- **Ontology summary:** hand-curated static file (`prompts/ontology-summary.md`, ~400 tokens). Loaded once at process start, injected into every prompt.

## How to run

### 1 — Full pipeline (real LLM + real GraphDB)

Needs `backend/.env` with `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY`) filled in.

```powershell
# Terminal 1 — backend
cd backend; uv run fastapi dev app/main.py

# Terminal 2 — frontend
cd frontend; pnpm dev
```

Open `http://localhost:5173`. Select provider/model from the dropdown, submit a question.

### 2 — Frontend UI iteration (mock API, no backend needed)

```powershell
cd frontend; $env:VITE_USE_MOCK_API='1'; pnpm dev
```

Streams canned SPARQL character-by-character, then shows a hard-coded results table. No network calls, no API key required. Use this for CSS/layout work.

### 3 — Backend only with fake LLM (no API key, no frontend)

```powershell
cd backend
# in .env: LLM_PROVIDER=fake
uv run fastapi dev app/main.py
```

Test the API directly:
```powershell
Invoke-RestMethod -Method POST -Uri http://localhost:8000/query `
  -ContentType 'application/json' `
  -Body '{"question":"test","provider":"fake","model":"fake-v1"}'
```

### 4 — Run tests

```powershell
cd backend
uv run pytest -v -m "not live"    # fast, no API keys needed (64 tests)
uv run pytest -m live             # hits real GraphDB + LLM APIs (3 tests, costs tokens)
```

Live tests need the relevant API key exported into the shell **before** running pytest (pytest does not auto-load `.env`):
```powershell
$env:ANTHROPIC_API_KEY = (Get-Content .env | Select-String '^ANTHROPIC_API_KEY=' | ForEach-Object { ($_ -split '=',2)[1] })
uv run pytest -m live -v
```

## Where to find more

- `backend/CLAUDE.md` — Python/FastAPI specifics
- `frontend/CLAUDE.md` — React/Vite specifics
- `thesis/CLAUDE.md` — writing rules, chapter structure, citation style
- `decisions/` — every real technical decision, numbered and dated
- `notes/PROGRESS.md` — what's been done and what's next (read this first each session!)
