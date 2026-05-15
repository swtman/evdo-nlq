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

## 2026-05-16 — Frontend: Playwright bug-hunt, features, sidebar refactor, code docs

### Done
- **Playwright live testing** — discovered and fixed 5 bugs in the live pipeline:
  1. `"inputTokens"` literal text rendered in results metadata (JSX typo).
  2. Fake LLM seconds (`tokens/1000`) removed — no real timing data in SSE events.
  3. Example query click didn't update the input field — added `prefillQuestion` prop to `QueryForm`.
  4. Example suggestions contained NOT_ANSWERABLE topics — replaced with working queries.
  5. Clicking a history item left the input showing the previous query — `handleHistorySelect` now sets `prefillQuestion`.
- **3 CSS bugs fixed:**
  - Active sidebar item text cropped (negative-margin clipped by implicit `overflow-x: auto`) → removed `-14px` margin, 3px border with adjusted padding instead.
  - Sidebar background not filling when page content taller than viewport → CSS `linear-gradient` on `.app-frame`.
  - NOT_ANSWERABLE long comment causing horizontal scroll in SPARQL panel → `white-space: pre-wrap`.
- **Clear button** (`✕ εκκαθάριση`) added next to ΑΝΑΖΗΤΗΣΗ; wired through `useQueryStream.clear()`.
- **Sidebar refactor** (ADR-009): permanent 220px left column replaced with header-toggle overlay. Layout changed from `grid 220px 1fr` to single-column `display: block`. Eliminates height-fill, clip, and scroll bugs permanently.
- **Code documentation**: beginner-friendly JSDoc + inline comments added to all 22 frontend source files (`*.ts`, `*.tsx`, `styles.css`). File-level headers, field-level comments on all types, non-obvious logic explained.
- **`frontend/FRONTEND-GUIDE.md`** written (high-level architecture guide for new contributors).
- **ADR-008** (parchment-brutalist aesthetic) added to `decisions/README.md` index.
- **ADR-009** (`decisions/009-sidebar-as-overlay.md`) written.
- **`frontend/CLAUDE.md`** updated to match current codebase (new folder structure, new components, state machine, design tokens, dual-display path, history, what-not-to-do).

### Next
1. Add vitest + `@testing-library/react` and write unit tests for `useHistory`, `useSortedPaged`, `exporters.ts`.
2. Wire `VITE_GIT_SHA` in `vite.config.ts` so the build version chip shows a real SHA.
3. Begin thesis writing — Ch 02 (Background) and Ch 04 (System Design from ADRs).
4. Decide v2 vs v3 as default production prompt.

### Blockers / notes
- Frontend is not yet tested with a unit test harness (no vitest configured). `pnpm typecheck` is the only automated gate.
- The `llmSecs` display (token-based estimate) was removed; the `done` SSE event has no wall-clock timing. If timing is needed later, the backend should add it to the `done` payload.
- The sidebar toggle uses `≡ ιστορικό (n)` in the header; the history is still in `localStorage` so it persists across reloads.

---

## 2026-05-15 — Frontend revamp: parchment-brutalist design system

### Done
- Full CSS rewrite (`styles.css`) with parchment-brutalist design tokens (light + dark themes), animations, paper-grain texture.
- New `types.ts` additions: `HistoryEntry`, `SortState`, `ColumnVisibility`.
- `App.tsx` restructured to sidebar + main grid layout with history integration.
- `i18n/el.ts` extended with all new translation keys.
- `useHistory` hook — localStorage-backed, 20-item FIFO cap, persists across reloads.
- `HistorySidebar` component — session history with search, active highlight, clear.
- `QueryForm` restyled — `›` prefix, label-prefixed selects, burnt-orange submit.
- `SparqlPanel` — copy button with "✓ αντιγράφηκε" feedback, `// generating…`/`// ready` status.
- `ErrorBanner` — `// σφάλμα:` prefix, parchment styling, dismissable.
- `ResultsTable` refactored into `ResultsTable/` subcomponents:
  - `useSortedPaged` hook (numeric-aware, Greek locale, row-coherent sort)
  - `SortIcon`, `Pagination`, `ColumnsMenu`, `ExportMenu`, `EmptyState`
  - Pagination 10/25/50/100 rows, numbered page buttons
  - 4-format export (CSV/JSON/XML/TSV) of all rows via `utils/exporters.ts`
  - Staggered row fade-in animation
  - Column visibility (resets per query)
- Mobile breakpoint (<640px): sidebar collapses to overlay, form stacks, table scrolls horizontally.
- `docs/superpowers/specs/2026-05-15-frontend-revamp-design.md` written.
- `decisions/008-frontend-aesthetic-parchment-brutalist.md` written.
- `pnpm typecheck` passes clean.

### Next
1. Open `http://localhost:5173` (mock mode) and verify UI manually.
2. Add vitest and write unit tests.
3. Test with real backend.

### Blockers / notes
- No vitest configured yet.
- `GIT_SHA` in App.tsx reads from `VITE_GIT_SHA` — needs `vite.config.ts` define block.

---

## 2026-05-14 — Docs catch-up: ADR-007, TODO and PROGRESS refresh

### Done
- Wrote ADR-007 (`decisions/007-anthropic-prompt-caching.md`): documents the `cache_control: ephemeral` decision, model floor constraints (Sonnet active, Haiku no-op), and DiskCache interaction.
- Added ADR-007 row to `decisions/README.md` index.
- Updated `TODO.md`: Phase 3 marked ✅ with v2/v3 entries, Phase 5 items correctly checked, new Phase 5b section for cost/latency work.
- Appended missing PROGRESS entries (2026-05-04 through 2026-05-08).

### Next
1. Decide v2 vs v3 as default production prompt; update root CLAUDE.md.
2. Run a side-by-side Haiku vs Sonnet eval run and document findings (Phase 5 compare item).
3. Begin thesis writing — Ch 02 (Background) and Ch 04 (System Design from ADRs).

### Blockers / notes
- Internship starts 2026-05-18 — 4 days out. MVP is stable and eval is at 84%.
- ADR for thesis format (LaTeX vs Markdown+Pandoc) still missing — pick one before writing starts.

---

## 2026-05-08 — Prompt v3 + eval at 84% result-set match (Sonnet/English)

### Done
- Added `prompts/nl-to-sparql-v3.md`: three rule changes driven by v2 failure analysis.
  - Rule 10 split: scalar COUNT stays flat with `COUNT(DISTINCT)` directly; GROUP_CONCAT subquery pattern is separate.
  - Rule 11 scoped: inner-SELECT-DISTINCT dedup applies to GROUP_CONCAT only, not scalar counts.
  - Rule 13 added: FILTER EXISTS/NOT EXISTS scope must escalate with question granularity (module → department → university).
- Fixed gold entries for ex-001 and ex-016 in `prompts/examples.yaml`.
- Eval run: v3 / Sonnet 4.6 / English → **84% result-set match (16/19)**. Report: `notes/eval-runs/2026-05-08-v3-english-claude-claude-sonnet-4-6.md`.
- Per-shape 100%: not-answerable, traversal-lookup, set-difference-by-year, set-intersection-by-book, negative-existence, multi-level-aggregate-with-concat.
- Remaining gaps: multi-book-comparison (0%), multi-level-count (50%), set-difference-by-book (67%).

### Next
1. Investigate remaining 3 failure shapes for thesis Chapter 6.
2. Write ADR for prompt caching and thesis format.
3. Decide production default: v2 vs v3.

### Blockers / notes
- Previous (pre-comparison-fix) eval baselines: v2/Haiku = 26%, v2/Sonnet = 42%. Post-fix v3/Sonnet = 84%.
- `cache_creation_input_tokens` and `cache_read_input_tokens` visible in INFO logs from this session onward.

---

## 2026-05-07 — Anthropic prompt caching on system prefix

### Done
- Added `cache_control: {"type": "ephemeral"}` to the `system` block in both `ClaudeProvider.generate()` and `ClaudeProvider.stream()` (commit `6af93dc`).
- Stable prefix (rules + ontology + 6 few-shot examples) is ~3 744 tokens — above the 2 048-token Sonnet 4.6 floor, below the 4 096-token Haiku 4.5 floor.
- Extended INFO log lines with `cache_write=` and `cache_read=` fields.
- No changes to `LLMProvider` protocol, DiskCache, or any other provider.

### Next
1. Run eval harness and confirm `cache_read` count equals N−1 for an N-example run within 5 minutes.
2. Write ADR-007 documenting this decision.

### Blockers / notes
- DiskCache (sha256-keyed) still wraps every call. Anthropic cache only matters on DiskCache misses.
- Haiku runs silently skip caching; no penalty.

---

## 2026-05-04 — Eval methodology (ADR-005) + static few-shot v2 (ADR-006)

### Done
- Created `prompts/examples.yaml` with 21 gold examples across 9 query shapes (traversal-lookup, negative-existence, multi-level-aggregate-with-concat, set-difference-by-year, set-difference-by-book, set-intersection-by-book, multi-level-count, multi-book-comparison, not-answerable).
- Built `backend/scripts/eval.py`: runs gold examples through the pipeline, compares result-sets (primary) and AST (secondary), writes a provenance-stamped Markdown report to `notes/eval-runs/`.
- Eval flags: `--prompt-version`, `--provider`, `--model`, `--language`, `--no-cache`, `--example-id`, `--shape`, `--no-skip-eval`.
- Baseline runs: v1/Haiku ≈ 0%, v2/Haiku/English = 26%.
- Wrote ADR-005 (eval methodology: result-set match primary) and ADR-006 (static few-shot v2, deferred dynamic retrieval).
- Corrected comparison logic (positional result matching); discovered gold entries ex-001 and ex-016 had broken gold — excluded from metrics (`broken_gold=True`).

### Next
1. Run v2 vs v3 comparison on Sonnet to quantify rule improvements.
2. Write ADR for prompt caching (feature already on the branch).

### Blockers / notes
- Gold execution failures are excluded from accuracy denominator (`broken_gold=True` → not a model failure).
- `comparison_mode` values validated at startup — typos exit immediately.

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

## 2026-05-15 — Frontend revamp: parchment-brutalist design system

### Done
- Full CSS rewrite (`styles.css`) with parchment-brutalist design tokens (light + dark themes), animations, paper-grain texture.
- New `types.ts` additions: `HistoryEntry`, `SortState`, `ColumnVisibility`.
- `App.tsx` restructured to sidebar + main grid layout with history integration.
- `i18n/el.ts` extended with all new translation keys.
- `useHistory` hook — localStorage-backed, 20-item FIFO cap, persists across reloads.
- `HistorySidebar` component — session history with search, active highlight, clear.
- `QueryForm` restyled — `›` prefix, label-prefixed selects, burnt-orange submit.
- `SparqlPanel` — copy button with "✓ αντιγράφηκε" feedback, `// generating…`/`// ready` status.
- `ErrorBanner` — `// σφάλμα:` prefix, parchment styling, dismissable.
- `ResultsTable` refactored into `ResultsTable/` subcomponents:
  - `useSortedPaged` hook (numeric-aware, Greek locale, row-coherent sort)
  - `SortIcon`, `Pagination`, `ColumnsMenu`, `ExportMenu`, `EmptyState`
  - Pagination 10/25/50/100 rows, numbered page buttons
  - 4-format export (CSV/JSON/XML/TSV) of all rows via `utils/exporters.ts`
  - Staggered row fade-in animation
  - Column visibility (resets per query)
- Mobile breakpoint (<640px): sidebar collapses to overlay, form stacks, table scrolls horizontally.
- `docs/superpowers/specs/2026-05-15-frontend-revamp-design.md` written.
- `decisions/008-frontend-aesthetic-parchment-brutalist.md` written.
- `pnpm typecheck` passes clean.

### Next
1. Open `http://localhost:5174` (mock mode) and verify UI manually — pagination, sort, export, history.
2. Add vitest + testing-library and write unit tests for `useHistory`, `useSortedPaged`, `exporters.ts`.
3. Test with real backend: `uv run fastapi dev app/main.py` + submit a real Greek query.
4. Commit the revamp on a feature branch and open a PR.

### Blockers / notes
- No vitest configured yet — package.json has no test script. Will need `vitest`, `@testing-library/react`, `jsdom` added.
- `GIT_SHA` in App.tsx reads from `VITE_GIT_SHA` env var. Add `define: { 'import.meta.env.VITE_GIT_SHA': JSON.stringify(execSync('git rev-parse HEAD').toString().trim()) }` to `vite.config.ts` to populate it at build time.
- The mock `llmSecs` calculation in ResultsTable.tsx uses token counts as a rough proxy — replace with actual wall-clock time from the `done` SSE event when available from the backend.

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
