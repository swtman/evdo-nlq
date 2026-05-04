# TODO — evdograph-nlq
> Rarely advise this file, this is mostly for my to keep track of what i have already done and what is up next
> Keep this file honest. Check items off as they're done, move completed phases to the bottom.
> When in doubt about what to do next, read this file first, then `notes/PROGRESS.md` for the most recent session's details.

---

## Phase 0 — Setup & Verification ✅ (mostly done)

- [x] Decide stack and write ADRs 001, 002, 003
- [x] Scaffold repo structure (CLAUDE.md files, decisions/, prompts/, notes/, scripts/)
- [x] Confirm GraphDB endpoint is reachable (`scripts/sparql_hello.py` — Q1 & Q2 pass)
- [x] Virtual environments set up for `backend/` and `scripts/` via `uv`
- [x] Push scaffolded repo to GitHub

---

## Phase 1 — Ontology Exploration

- [x] Run `scripts/explore_ontology.py` to dump classes + properties into `notes/ONTOLOGY-NOTES.md`
- [x] Fill in the real namespace/prefix for EvdoGraph in `ONTOLOGY-NOTES.md`
- [x] Confirm exact class URIs and property URIs (replace educated guesses in ONTOLOGY-NOTES.md)
- [x] Write 3–5 hand-crafted SPARQL queries that answer real questions → these become few-shot examples

---

## Phase 2 — Backend (FastAPI)

> All code goes under `backend/app/`. Follow the layout in `backend/CLAUDE.md`.

- [x] Create `backend/app/config.py` — Pydantic settings (reads from `.env`)
- [x] Create `backend/app/main.py` — FastAPI app entrypoint, CORS
- [x] Create `backend/app/api/query.py` — `POST /query` endpoint
- [x] Create `backend/app/llm/base.py` — `LLMProvider` protocol + `LLMResponse` dataclass
- [x] Create `backend/app/llm/fake_provider.py` — returns canned SPARQL, no network
- [x] Create `backend/app/llm/cache.py` — disk cache keyed on `sha256(system + user + model)`
- [x] Create `backend/app/llm/claude_provider.py` — Anthropic implementation (uses cache)
- [x] Create `backend/app/sparql/client.py` — SPARQLWrapper client with error handling + retry
- [x] Create `backend/app/ontology/loader.py` — loads a compact ontology summary, cached in memory
- [x] Create `backend/app/prompts/loader.py` — reads versioned prompt files from `prompts/`
- [x] Copy `.env.example` to `.env` and fill in API key + endpoint
- [x] Write unit tests in `backend/tests/` using `FakeProvider`
- [x] Confirm `uv run fastapi dev app/main.py` starts without errors

---

## Phase 3 — Prompt Engineering

- [ ] Write/refine `prompts/nl-to-sparql-v1.md` with ontology summary + few-shot examples
- [ ] Test prompt manually: send a real NL question → get back valid SPARQL
- [ ] Measure token usage per query (log `input_tokens` / `output_tokens`)
- [ ] Iterate on prompt until Haiku produces correct SPARQL for at least 5 test questions

---

## Phase 4 — Frontend (React + Vite)

> Follow `frontend/CLAUDE.md`. Use `pnpm`.

- [x] Scaffold frontend with `pnpm create vite` (React + TypeScript)
- [x] Create a basic query input form (text box + submit button)
- [x] Wire form to `POST /query` on the backend
- [x] Display results in a table
- [x] Display the generated SPARQL (so the user can see what was run)
- [x] Basic error handling (show meaningful message if query fails)
- [x] Run `pnpm typecheck` with no errors

---

## Phase 5 — Integration & Evaluation

- [ ] Run the full pipeline end-to-end: NL → SPARQL → GraphDB → results in UI
- [ ] Build a small test set (20–30 NL questions with expected results)
- [ ] Measure accuracy: how often does Haiku produce correct SPARQL?
- [ ] Compare Haiku vs Sonnet on a subset — document findings
- [ ] Document failure modes in `notes/ONTOLOGY-NOTES.md` → feeds into thesis Chapter 6

---

## Phase 6 — Thesis Writing

- [ ] Write ADR-004 (thesis format)
- [ ] Chapter 01 — Introduction
- [ ] Chapter 02 — Background (NLQ, SPARQL, EvdoGraph)
- [ ] Chapter 03 — System Design (architecture, pipeline)
- [ ] Chapter 04 — Implementation
- [ ] Chapter 05 — Prompt Engineering
- [ ] Chapter 06 — Evaluation & Results
- [ ] Chapter 07 — Conclusion

---

## Deadlines

- **2026-05-18** — Internship starts; aim for MVP (Phases 0–4) done before this date.
