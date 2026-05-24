# ADR-010: Docker Compose as Reproducibility Packaging

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** @manoliss

## Context

The thesis supervisor and other developers need to run the full evdograph-nlq
stack (FastAPI backend + React frontend + optional local LLM) on their own
machine with minimal setup. Today the project requires installing uv, Node,
pnpm, and running two terminals manually. There is no version pin for Node or
pnpm, which causes "works on my machine" failures. Docker Compose was
considered as the single-command alternative.

## Options considered

### Option A — Docker Compose (production-style images)
- Pros: single `docker compose up`; hides runtime versions; platform-independent;
  supports optional Ollama service via profiles; images can be tagged/archived.
- Cons: Docker Desktop required (~3 GB install); image build adds 1–2 min
  first-run; native dev loop is slightly less ergonomic (keep running natively
  with uv + pnpm for active development).

### Option B — Makefile / shell script wrapper
- Pros: no Docker needed; thin layer over existing commands.
- Cons: still requires uv + Node + pnpm installed at correct versions; no
  isolation; fails silently on version mismatches; does not help with the
  Ollama service.

### Option C — Dev container (.devcontainer)
- Pros: full VS Code integration; single unified dev environment.
- Cons: significantly heavier setup; requires VS Code + Remote Containers
  extension; overkill for a thesis handoff scenario.

## Decision

We chose **Option A** (Docker Compose with production-style images).

The frontend image uses a multi-stage build (`node:20-alpine` builder →
`nginx:alpine` runtime) so the final image contains only the static build and
nginx, not Node or the source. The backend image uses `python:3.12-slim` with
`uv sync --frozen --no-dev` for a deterministic, minimal production image.

An `ollama` compose profile keeps the local-LLM service optional: users who
provide a cloud API key use the default profile; users without a key add
`--profile ollama`. A one-shot `ollama-init` service auto-pulls
`qwen2.5:3b-instruct` on first launch.

Docker is the handoff artifact. Active development continues using the native
`uv run fastapi dev` + `pnpm dev` workflow, which is faster for iteration.

## Consequences

- Recipient needs Docker Desktop; no other prerequisite.
- API keys stay in the local `.env`; never baked into images.
- `.env.example` is consolidated at repo root (single source of truth for both
  Compose and native-dev users).
- Native dev workflow (`uv run fastapi dev` from `backend/`) is unchanged.
- Node/pnpm versions are now pinned in `frontend/package.json` (`engines` +
  `packageManager`) and `frontend/.nvmrc`.

## Follow-ups

- [ ] Update `README.md` to lead with the Docker setup
- [ ] Update `CLAUDE.md` "How to run" section
- [ ] Add Docker section to thesis chapter on technical implementation
