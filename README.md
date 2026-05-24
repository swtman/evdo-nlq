# evdograph-nlq

Natural-language querying over **EvdoGraph**, the Knowledge Graph of books recommended by the Greek academic textbook system (Eudoxus).

A user types a question in plain Greek (or English). The system uses an LLM to translate the question into **SPARQL**, runs it against the EvdoGraph triple store, and displays the results.

Undergraduate thesis, Aristotle University of Thessaloniki, Computer Science Department, 2026.

## Motivation

EvdoGraph holds rich information about university textbooks, authors, publishers, and courses — but access is gated behind SPARQL, a query language most people don't know. This project bridges that gap by letting an LLM act as translator between natural language and SPARQL, using the EvdoGraph ontology as its schema guide.

## Architecture

```
React UI  →  FastAPI  →  LLM (NL + ontology → SPARQL)  →  GraphDB  →  results → UI
```

## Getting started

### Prerequisites

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — the only hard requirement for running the app.
- Git.

> **Active development?** See [Native dev setup](#native-dev-setup) below.

---

### 1 — Clone and configure

```powershell
git clone <repo-url>
cd evdograph-nlq
cp .env.example .env
```

Open `.env` and fill in your API key:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...   # or GEMINI_API_KEY if using Gemini
LLM_PROVIDER=claude            # or gemini
```

> **Security:** `.env` is gitignored. Never commit it, never paste keys into
> chat or issues. If a key leaks, revoke it immediately in the
> [Anthropic console](https://console.anthropic.com) or Google Cloud Console.

---

### 2a — Run with a cloud LLM key

```powershell
docker compose up
```

Open `http://localhost:5173`. Use the provider/model dropdown to select your
LLM. First build takes ~2 minutes; subsequent starts are instant.

---

### 2b — Run without any API key (local LLM via Ollama)

```powershell
docker compose --profile ollama up
```

This starts the full stack **plus** a local Ollama service. On first launch,
`qwen2.5:3b-instruct` (~2 GB) is downloaded automatically. Subsequent starts
are instant.

> **Quality note:** Small local models produce lower-quality SPARQL for Greek
> ontology queries compared to Claude/Gemini. Expect ~30–50% more errors.
> This path is intended for "see it work without a key," not for thesis
> evaluation runs.

---

### Eval track (comparing local vs. cloud SPARQL quality)

After starting with `--profile ollama`, pull a stronger model:

```powershell
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

Then run the eval harness:

```powershell
cd backend
$env:LLM_PROVIDER = "ollama"
$env:LLM_MODEL    = "qwen2.5:7b-instruct"
uv run python scripts/eval.py --prompt-version 2 --provider ollama --model qwen2.5:7b-instruct --language both
```

Eval reports are saved to `notes/eval-runs/` with full provenance (git SHA,
prompt hash, examples hash) so cloud and local runs are directly comparable.

---

### GPU acceleration (NVIDIA only)

If you have an NVIDIA GPU and Docker Desktop with WSL2:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up
```

See `docker-compose.gpu.yml` for prerequisites (WSL2 + NVIDIA Container Toolkit).
macOS Metal is not supported via Docker (Ollama supports Metal natively outside Docker).

---

### Native dev setup

For active development you do **not** need Docker. Run the services directly:

```powershell
# Terminal 1 — backend (hot reload)
cd backend
cp ..\\.env.example .env    # or copy root .env.example here
# Edit .env, add your API key
uv sync
uv run fastapi dev app/main.py

# Terminal 2 — frontend (hot reload)
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173`.

**UI-only iteration (no backend, no API key):**

```powershell
cd frontend; $env:VITE_USE_MOCK_API='1'; pnpm dev
```

---

### Running tests

```powershell
cd backend
uv run pytest -v -m "not live"    # 78+ tests, no API key needed
uv run pytest -m live             # hits real APIs (costs tokens)
```

## Project structure

- `backend/` — FastAPI service
- `frontend/` — React + Vite UI
- `thesis/` — thesis document (Greek)
- `decisions/` — ADRs (architecture decision records)
- `prompts/` — versioned LLM prompts
- `scripts/` — SPARQL and ontology helpers

## License

TBD.
