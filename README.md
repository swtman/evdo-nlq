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

See `CLAUDE.md` at the repo root for the full guide. Short version:

```bash
# backend
cd backend
uv sync
cp .env.example .env    # fill in ANTHROPIC_API_KEY
uv run fastapi dev app/main.py

# frontend (new terminal)
cd frontend
pnpm install
pnpm dev
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
