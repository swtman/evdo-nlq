# evdograph-nlq — Natural Language Queries on EvdoGraph

> Thesis project (AUTh CSD, 2026): users ask questions about Greek university textbooks in plain language; an LLM turns each question into SPARQL, it runs against EvdoGraph, and results are rendered in a web UI.

## Pipeline in one picture

```
User (NL, Greek/English)
  → React UI
  → FastAPI /query
  → LLMProvider (Claude / OpenAI / Deepseek)  ←  ontology summary + few-shot examples
  → SPARQL string
  → GraphDB endpoint (http://lod.csd.auth.gr:7200/repositories/Evdoxus)
  → results (JSON)
  → React UI (table + generated SPARQL shown)
```

## Stack at a glance

- **Backend:** Python 3.12, FastAPI, `rdflib`, `SPARQLWrapper`, `anthropic` SDK, `pytest`, `ruff`.
- **Frontend:** React 18 + Vite + TypeScript, plain CSS (no Tailwind unless decided later — see ADRs).
- **Triple store:** remote GraphDB at `http://lod.csd.auth.gr:7200/repositories/Evdoxus` — EvdoGraph repository. We do not self-host.
- **LLM:** pluggable (`LLMProvider` protocol). Default model for development: `claude-haiku-4-5`.
- **Package managers:** `uv` for Python, `pnpm` for Node.

## Repository map

| Path | What's there |
|------|--------------|
| `backend/` | FastAPI service, LLM providers, SPARQL client, prompt loading, cache |
| `frontend/` | React + Vite app |
| `thesis/` | Thesis document (Greek), chapter drafts, figures, cited PDFs |
| `decisions/` | Architecture Decision Records — read these to understand *why* code is shaped this way |
| `prompts/` | Versioned LLM prompt templates (each one is a file, never inlined in code) |
| `notes/` | Running notes: `PROGRESS.md` (session log), `ONTOLOGY-NOTES.md` (EvdoGraph schema notes) |
| `scripts/` | Standalone helpers (SPARQL smoke test, ontology introspection) |

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

- Default model for code development: **`claude-sonnet-4-6`**. Switch to `claude-opus-4-7`for planning and more complex tasks.
- Default model for generating the SPARQL queries from natural language : **`claude-haiku-4-5`**. Switch to `claude-sonnet-4-6` only for side-by-side comparisons or when Haiku clearly underperforms on SPARQL.
- **Cache all LLM responses on disk during dev** — same prompt hashes to the same response. The cache lives under `backend/.llm_cache/` (gitignored).
- **Fake provider for tests and frontend work.** Real API calls only when you are deliberately testing or measuring the pipeline.
- **Print token usage** for every real call (`response.usage.input_tokens` / `output_tokens`) — catch prompt bloat early.
- **Ontology probably won't fit whole in a prompt.** Plan for summarization / schema retrieval. This is a thesis-worthy problem on its own.

## How to run (dev)

```bash
# backend
cd backend && uv sync && uv run fastapi dev app/main.py

# frontend (new terminal)
cd frontend && pnpm install && pnpm dev
```

## Where to find more

- `backend/CLAUDE.md` — Python/FastAPI specifics
- `frontend/CLAUDE.md` — React/Vite specifics
- `thesis/CLAUDE.md` — writing rules, chapter structure, citation style
- `decisions/` — every real technical decision, numbered and dated
- `notes/PROGRESS.md` — what's been done and what's next (read this first each session!)
