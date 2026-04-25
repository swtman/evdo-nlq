# ADR-004: NLQ pipeline design — streaming, per-request provider, retry strategy, ontology loading

- **Status:** Accepted
- **Date:** 2026-04-25
- **Deciders:** @swtman

## Context

With the core abstractions in place (FastAPI — ADR-001, pluggable LLM — ADR-002, remote GraphDB — ADR-003), we needed to nail down four concrete pipeline choices before writing any application code:

1. How to surface SPARQL generation to the user (UX)
2. How the frontend selects the LLM provider and model
3. What to do when the LLM produces invalid SPARQL
4. How to supply the ontology schema to the prompt

---

## Decision 1 — SSE streaming for SPARQL generation

### Options considered

**Option A — Non-streaming: wait for full SPARQL, return JSON**
- Pros: Simple. No SSE machinery. Retry loop is trivial.
- Cons: The user stares at a spinner for 2–5 seconds. No visibility into what the model is doing.

**Option B — SSE streaming: stream SPARQL tokens, then stream results**
- Pros: User sees the query being written in real time — compelling for a thesis demo. Lets the UI layer show progress through each pipeline stage.
- Cons: Requires `POST + fetch/ReadableStream` on the frontend (browser `EventSource` only supports GET — noted as a revisit point for the React build). Retry must collect the full output before validating.

**Option C — WebSocket**
- Pros: Bidirectional, persistent.
- Cons: Overkill for a request/response pipeline. More complex to set up and test.

**Decision:** Option B (SSE). We also keep `POST /query` (non-streaming JSON) as a secondary endpoint for tests and programmatic use. The `sse-starlette` library handles SSE in FastAPI.

---

## Decision 2 — Per-request provider and model selection

### Options considered

**Option A — Provider fixed at startup via `.env`**
- Pros: Already designed in ADR-002. Simple.
- Cons: Comparing providers requires restarting the server. The thesis needs side-by-side comparison, not restart-and-repeat.

**Option B — Provider and model passed in each `POST /query` request; UI shows a dropdown**
- Pros: User can switch Haiku ↔ Sonnet ↔ fake mid-session without a restart. Provider comparison becomes a first-class UI feature — a direct thesis contribution.
- Cons: `ProviderFactory` must create a new provider instance per request rather than using a startup singleton.

**Decision:** Option B. `QueryRequest` carries `provider: str` and `model: str`. `ProviderFactory.get(name, model)` creates the right implementation. The env defaults are kept as fallbacks.

---

## Decision 3 — Single-turn retry on invalid SPARQL

### Options considered

**Option A — New single-turn call with error injected**
- System prompt: same nl-to-sparql rules. User message: original question + failed SPARQL + parse error.
- Pros: Protocol stays `generate(system, user)` — no changes to the LLMProvider interface. Simple to reason about.
- Cons: Model loses the conversational context of "I just tried this."

**Option B — Multi-turn conversation (assistant turn = failed SPARQL, user turn = error)**
- Pros: More natural for Claude. Model has full context.
- Cons: Requires extending `LLMProvider.generate` to accept a message list, changing the interface for all providers. Larger scope for v1.

**Decision:** Option A. Max 2 retry attempts. The retry uses a separate prompt file (`nl-to-sparql-retry-v1.md`) so the injection strategy is versioned. Multi-turn is documented as a future enhancement (TODO in `api/query.py`).

---

## Decision 4 — Static ontology summary file

### Options considered

**Option A — Static file (`prompts/ontology-summary.md`)**
- Loader reads the file once at first call, caches in a module-level variable.
- Pros: Zero startup latency. No dependency on GraphDB being reachable at boot. Summary is hand-curated and stable.
- Cons: Must be updated manually if the ontology changes (acceptable — EvdoGraph is read-only in our use case).

**Option B — Live introspection at startup (SPARQL queries to build summary)**
- Pros: Always fresh.
- Cons: Adds 3–5 seconds to startup. Fails if GraphDB is unreachable. The ontology does not change.

**Option C — Hybrid with freshness timestamp**
- Pros: Best of both.
- Cons: Engineering overhead not justified for a static dataset.

**Decision:** Option A. The ontology is fixed; a static hand-curated summary is more predictable and cheaper than live introspection.

---

## Consequences

- `POST /query/stream` is the canonical endpoint; `POST /query` is a test-friendly alias.
- Frontend must use `fetch + ReadableStream` for SSE (not `EventSource`) — **revisit when building the React query hook.**
- `ProviderFactory` is instantiated per request, not as a startup singleton.
- `LLMProvider` protocol gains a `stream()` method alongside `generate()` — additive, no breaking change.
- Retry prompt logic lives in `prompts/nl-to-sparql-retry-v1.md`, decoupled from application code.
- `ontology/loader.py` has no network dependency; backend starts instantly.

## Follow-ups

- [x] Write spec to `docs/superpowers/specs/2026-04-25-backend-design.md`
- [x] Add `sse-starlette` to `pyproject.toml`
- [x] Create `prompts/nl-to-sparql-retry-v1.md`
- [x] Create `prompts/ontology-summary.md` (promoted compact block from `notes/ONTOLOGY-NOTES.md`)
- [x] Update `backend/CLAUDE.md` to document the streaming endpoint and per-request provider selection
- [x] Add ADR-004 to `decisions/README.md`
