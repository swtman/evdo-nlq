# Progress log

_At the end of every coding session, append a new entry. Keep it short. This is what you read first when you sit back down._

## How to use this file

Each session = one H2 section. Three H3s: **Done**, **Next**, **Blockers/notes**. The next-session-you (or next Claude) reads the top entry and knows exactly what to pick up.

Template:

```markdown
## YYYY-MM-DD — <one-line summary of session focus>

### Done
- Bullet points of what was finished.

### Next
- What to do next session, in rough priority order.

### Blockers / notes
- Anything unresolved, weird, or worth remembering.
```

---

## 2026-05-03 — Backend architectural refactor (5 anti-patterns fixed)

### Done
- **AP2 — StreamResult:** Added `StreamResult` dataclass to `app/llm/base.py`; changed `LLMProvider.stream()` return type from `Iterator[str]` to `StreamResult`. All providers updated (Claude, Gemini, Fake). Removed `last_input_tokens`/`last_output_tokens` side-effect attributes from provider instances.
- **AP5 — Prompt cache:** Added module-level `_cache` dict to `app/prompts/loader.py`; templates now read from disk once per process (mirrors `ontology/loader.py` pattern).
- **AP1+AP4 — QueryPipeline:** Extracted all business logic from `app/api/query.py` into new `app/pipeline/query_pipeline.py`. `QueryPipeline` owns retry loop, prompt loading, SPARQL validation, and execution. Route handlers are now 3–5 line wrappers. `SparqlClient` is now injected via `_make_pipeline()` instead of instantiated inside business logic. Streaming path uses typed event objects (`TokenEvent`, `RetryEvent`, `CompleteEvent`, `ResultsEvent`, `DoneEvent`) — zero SSE concerns inside the pipeline.
- **AP3 — Event loop:** `stream_events()` upgraded from sync `Iterator` to `async` generator; each token's `next()` call runs in a thread pool via `asyncio.get_running_loop().run_in_executor(None, next, it, sentinel)`.
- **Tests:** 50 non-live tests pass (was 40). Added `test_query_pipeline.py` (7 tests, sync + async). Added `StreamResult` field tests, prompt cache test. Fixed `NotAnswerableProvider` in endpoint tests.
- Removed debug `print` statement from old `query.py`.

### Next
1. Commit and tag v0.1 (full pipeline working end-to-end).
2. Deploy backend to staging (GitHub Actions CI).
3. Begin thesis authoring phase.

### Blockers / notes
- No blockers. All 50 tests green, ruff clean.

---

## 2026-05-01 — Full pipeline live-tested; SSE parser fixed; CLAUDE.md updated

### Done
- Ran live end-to-end pipeline test (Claude + GraphDB): backend returns correct SSE events.
- Fixed `frontend/src/api/client.ts` SSE parser: `sse_starlette` uses `\r\n\r\n` event separators, not `\n\n`. Parser now normalizes CRLF → LF after every chunk so events split correctly. Also flushes remaining buffer on stream close so the final `done` event is never lost.
- Updated all CLAUDE.md files (root, backend/, frontend/) to reflect: full pipeline status, all three run modes (full/fake-backend/mock), GeminiProvider, live-test instructions, SSE parser quirk.

### Next
1. Commit and tag v0.1 (full pipeline working end-to-end).
2. Deploy backend to staging (GitHub Actions CI).
3. Begin thesis authoring phase.

### Blockers / notes
- Live tests need API keys exported into the shell before running pytest (`.env` is not auto-loaded by pytest).
- `input_tokens` / `output_tokens` in the `done` event read 0 when the disk cache is hit — not a bug, cached responses bypass the API so there are no real token counts.

---

## 2026-05-01 — Frontend MVP complete (React + Vite + TypeScript)

### Done
- **Scaffold:** Vite + React 18 + TypeScript, dev server on :5173, `pnpm typecheck` gate.
- **Components (all accessible + dark theme):**
  - `QueryForm.tsx` — controlled input, provider/model dropdowns from `GET /providers`, submit button (disabled while streaming).
  - `SparqlPanel.tsx` — collapsible SPARQL display with blinking cursor `▌` while streaming, emerald accent, status pills (`● Generating` / `✓ Complete`), aria-expanded.
  - `ResultsTable.tsx` — table from `{ columns, rows }` with footer token counts + retry count, blue accent. Empty state: "Δεν βρέθηκαν αποτελέσματα."
  - `ErrorBanner.tsx` — dismissible alert with `role="alert"`, accessible dismiss button.
- **State management:** `useQueryStream()` hook with `useReducer` (state machine: idle → streaming → done/error), handles SSE event dispatch, `AbortController` lifecycle (unmount + new submit).
- **API:** `src/api/client.ts` parses SSE via `fetch + ReadableStream` (POST to `/query/stream`). Delegates to `src/api/mock.ts` when `VITE_USE_MOCK_API=1` (canned events for UI development).
- **i18n:** All Greek strings centralized in `src/i18n/el.ts` (title, buttons, labels, error messages).
- **Styling:** Plain CSS with dark theme (--bg: #111827, --panel: #1f2937, --emerald: #10b981, --blue: #3b82f6), gradient logo, responsive panels.
- **Types:** Discriminated union `QueryState` for type-safe conditional rendering.
- **Build:** Vite dev proxy for `/query` and `/providers` endpoints to localhost:8000.
- All typecheck passes, accessibility verified (ARIA labels, alerts, button semantics).

### Next
1. Merge frontend MVP to main (all features complete, tested, ready for internship).
2. Deploy backend to staging (set up GitHub Actions CI if not done).
3. Run thesis authoring phase after stable release.

### Blockers / notes
- Internship starts 2026-05-18 — MVP is now stable and ready.
- Backend tests: 39/40 pass (1 pre-existing failure in `test_settings_defaults`; unrelated to frontend).
- GeminiProvider confirmed working as free LLM alternative.

---

## 2026-04-30 — GeminiProvider added (free alternative to Claude)

### Done
- Designed and implemented `GeminiProvider` using `google-genai>=1.0` SDK.
- `generate()` and `stream()` both wrap `DiskCache`, mirror `ClaudeProvider` patterns, set `last_input_tokens`/`last_output_tokens`.
- Registered in `factory.py` under `"gemini"`, listed in `GET /providers` dropdown with `gemini-2.0-flash` and `gemini-1.5-flash`.
- `GEMINI_API_KEY` added to `Settings` and `.env.example`.
- 5 unit tests + 1 `@pytest.mark.live` test — 39/40 non-live tests pass (1 pre-existing failure in `test_settings_defaults` due to local `.env`).
- Design spec: `docs/superpowers/specs/2026-04-30-gemini-provider-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-30-gemini-provider.md`

### Next
1. Get a free Gemini API key at https://aistudio.google.com/apikey, add to `.env`, run `uv run pytest -m live -v` to confirm full pipeline works end-to-end.
2. Push to GitHub (remote not yet set up).
3. Start the frontend — React + Vite scaffold, then the query hook using `fetch + ReadableStream` for SSE.

### Blockers / notes
- Internship starts 2026-05-18 — frontend MVP must be stable before then (~2.5 weeks).
- `test_settings_defaults` fails because local `.env` has `LLM_PROVIDER=fake`. Fix: either patch env in the test or temporarily rename `.env` when running that test.
- SSE transport: frontend must use `fetch + ReadableStream`, NOT `EventSource` (GET-only).

---

## 2026-04-25 — Backend pipeline complete

### Done
- Full backend pipeline implemented (16 tasks, all tests green).
- config.py, LLMProvider protocol, FakeProvider, ClaudeProvider (generate + stream), DiskCache.
- PromptLoader (strips frontmatter, extracts # System, safe SPARQL fill), OntologyLoader (static file, module-level cache).
- SparqlClient (rdflib offline validation + SPARQLWrapper execution), ProviderFactory.
- POST /query (sync JSON, retry logic, _clean_sparql, _is_not_answerable).
- POST /query/stream (SSE, token streaming, non-streaming retry, done event with token counts).
- GET /providers (static list for UI dropdown).
- prompts/nl-to-sparql-retry-v1.md, prompts/ontology-summary.md created.
- 33 non-live tests pass; 2 live tests available with `uv run pytest -m live`.
- git repo initialized at monorepo root; all commits on master.

### Next
1. Push to GitHub (create remote, `git push -u origin master`).
2. Run live tests: `uv run pytest -m live` (needs GraphDB up + ANTHROPIC_API_KEY in .env).
3. Start the frontend — React + Vite scaffold.
4. Build the React query hook using `fetch + ReadableStream` for POST /query/stream (see TODO in query.py).

### Blockers / notes
- Internship starts 2026-05-18 — frontend MVP must be stable before then.
- SSE transport: frontend must use `fetch + ReadableStream`, NOT `EventSource` (GET-only).
- GitHub remote not yet set up (gh CLI not installed; create repo at github.com then push manually).

---

## 2026-04-25 — GraphDB endpoint confirmed reachable

### Done
- Ran `scripts/sparql_hello.py` against `http://lod.csd.auth.gr:7200/repositories/Evdoxus`.
- Queries 1 (triple count) and 2 (top classes by instance count) passed — endpoint is up and returning data.

### Next
1. Run `scripts/explore_ontology.py` to dump classes/properties into `notes/ONTOLOGY-NOTES.md`.
2. Push the scaffolded repo to GitHub.

### Blockers / notes
- the endpoint itself is confirmed working.
- Remember: internship starts 2026-05-18; MVP needs to be stable before then.

---

## 2026-04-22 — Project scaffolded

### Done
- Decided stack: Python + FastAPI + rdflib, React + Vite + TS, GraphDB remote endpoint, pluggable LLM default to Claude Haiku.
- Scaffolded the full repo: CLAUDE.md files, decisions/, prompts/, notes/, scripts/.
- Wrote ADRs 001 (Python/FastAPI), 002 (pluggable LLM), 003 (remote GraphDB).

### Next
1. Install `uv` and `pnpm` locally if not already.
2. Run `scripts/sparql_hello.py` to confirm the GraphDB endpoint is reachable from your machine. **This is the first real check.** If this fails, everything after is blocked.
3. Figure out the exact repository path at `lod.csd.auth.gr:7200` — probably `/repositories/evdograph` but verify in GraphDB Workbench.
4. Run `scripts/explore_ontology.py` to dump the list of classes and properties into `notes/ONTOLOGY-NOTES.md`.
5. Push the scaffolded repo to GitHub.
6. Start Claude Code in the project folder and verify it picks up CLAUDE.md (`/status` should show it in context).

### Blockers / notes
- Haven't confirmed GraphDB repo path yet.
- Thesis format (LaTeX vs Markdown+Pandoc) still TBD.
- Internship starts 2026-05-18; plan to stabilise the MVP before then and shift to thesis-writing-heavy mode after.
