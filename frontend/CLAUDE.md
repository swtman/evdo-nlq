# frontend/ — React + Vite UI

Single-page app: natural-language input form → live SPARQL streaming panel → results table with sort/pagination/export, with error handling and query history. Revamped to parchment-brutalist design (ADR-008).

## Stack

- React 19 + TypeScript
- Vite (dev server on :5173, hot reload, build with `pnpm build`)
- Plain CSS (parchment-brutalist design system with CSS variables — no Tailwind)
- `fetch` + `ReadableStream` for SSE (not `EventSource` — backend uses POST)
- Custom `useQueryStream` hook with `useReducer` state machine
- `useHistory` hook with localStorage persistence (20-item FIFO)

## Folder structure

```
src/
├── main.tsx                        React 19 entrypoint, mounts App in StrictMode
├── App.tsx                         Layout shell: overlay + main column; dual display path (live vs. cached)
├── types.ts                        QueryState discriminated union, HistoryEntry, SortState, ColumnVisibility
├── styles.css                      Parchment-brutalist design tokens (light/dark), animations, all component styles
├── vite-env.d.ts                   Vite env type augmentation (VITE_USE_MOCK_API, VITE_GIT_SHA)
├── components/
│   ├── QueryForm.tsx               Input + provider/model dropdowns + submit + clear buttons
│   ├── SparqlPanel.tsx             Collapsible SPARQL display, streaming cursor, copy button, GraphDB bar
│   ├── ResultsTable/
│   │   ├── ResultsTable.tsx        Orchestrator: owns sort, page, column visibility, dropdown open state
│   │   ├── Pagination.tsx          Page-size selector + numbered page buttons
│   │   ├── ColumnsMenu.tsx         Dropdown checklist for showing/hiding columns
│   │   ├── ExportMenu.tsx          Dropdown for CSV/JSON/XML/TSV download (all rows, not just current page)
│   │   └── EmptyState.tsx          Zero-result block with 3 clickable example queries
│   ├── HistorySidebar.tsx          Overlay panel content: search input, entry list, clear button
│   ├── SortIcon.tsx                Inline SVG for idle/asc/desc sort states (mirrors public/*.png icons)
│   └── ErrorBanner.tsx             Dismissable error with `// σφάλμα:` prefix
├── hooks/
│   ├── useQueryStream.ts           SSE state machine (useReducer + AbortController lifecycle + /providers fetch)
│   ├── useHistory.ts               localStorage-backed query history, 20-item FIFO cap
│   └── useSortedPaged.ts           Memoised sort + pagination logic (numeric-aware, Greek locale)
├── api/
│   ├── client.ts                   SSE parser via fetch + ReadableStream; delegates to mock when VITE_USE_MOCK_API=1
│   └── mock.ts                     Canned SPARQL stream (18ms/char typewriter) + 46-row result set; no network calls
├── utils/
│   └── exporters.ts                toCSV / toJSON / toXML / toTSV + downloadBlob helper
└── i18n/
    └── el.ts                       All UI strings in Greek (single source of truth)
```

## Commands

```powershell
pnpm dev                  # dev server on http://localhost:5173
pnpm build                # production build (dist/)
pnpm preview              # serve production build
pnpm typecheck            # tsc --noEmit — run before every commit
```

## Running modes

### Mode 1 — Full pipeline (real LLM + real GraphDB)

Requires a running backend with API key in `backend/.env`.

```powershell
# Terminal 1
cd backend; uv run fastapi dev app/main.py

# Terminal 2
cd frontend; pnpm dev
```

### Mode 2 — Mock API (no backend, no API keys)

```powershell
cd frontend; $env:VITE_USE_MOCK_API='1'; pnpm dev
```

`VITE_USE_MOCK_API=1` makes `client.ts` delegate to `mock.ts` (dynamic import — never bundled in production). Streams canned SPARQL character-by-character then emits a 46-row result set. Covers: streaming cursor, GraphDB bar, pagination, sort, export, history.

Does **not** cover: retry UI, NOT_ANSWERABLE paths — test those with the real backend.

### Mode 3 — Fake LLM backend (no API key, real GraphDB)

```powershell
cd backend
$env:LLM_PROVIDER='fake'; uv run fastapi dev app/main.py
cd frontend; pnpm dev
```

## API contract

**Providers:** `GET /providers` → `{ providers: [{ id, models[] }] }`

**Query stream:** `POST /query/stream` (proxied by Vite to `http://localhost:8000`)

Request body: `{ question: string, provider: string, model: string }`

| SSE event | Data | Purpose |
|---|---|---|
| `sparql_token` | token text | Append to streaming SPARQL |
| `sparql_complete` | final SPARQL string | Replace streaming SPARQL; start GraphDB bar |
| `sparql_retry` | `{ attempt, error }` | Not yet surfaced in UI |
| `results` | `{ columns: string[], rows: Record<string,string\|undefined>[] }` | Populate results table |
| `done` | `{ provider, model, input_tokens, output_tokens, retries }` | Show token counts, transition to done |
| `error` | `{ message: string }` | Display ErrorBanner, transition to error state |

### SSE parser note

`sse_starlette` uses `\r\n` line endings and `\r\n\r\n` event separators. `client.ts` normalises `\r\n → \n` after every `reader.read()` call. Also: multi-line `data:` fields are concatenated; the buffer's final fragment is flushed when the stream closes so the `done` event is never lost. A `finally` block always calls `reader.releaseLock()`.

## State machine (`useQueryStream`)

```
idle → (submit) → streaming → (COMPLETE) → streaming (executing=true)
                            → (RESULTS)  → streaming (executing=false)
                            → (DONE)     → done
                            → (ERROR)    → error
done / error → (clear / dismissError) → idle
```

The `streaming` state accumulates `columns` and `rows` so the `DONE` action can read them when it fires. `executing` is the flag that shows/hides the GraphDB progress bar.

## Dual display path (App.tsx)

When the user clicks a history entry, `cachedResult` is set in App. All derived display values (`sparqlToShow`, `displayColumns`, `displayRows`) use `??` so `cachedResult` takes precedence over live `state`. The `(αποθηκευμένο)` badge in the results panel signals a cached view. Submitting a new query clears `cachedResult`.

## Query history

- `useHistory` reads/writes `localStorage` key `evdograph.history`.
- 20-item FIFO cap; oldest entry dropped when full.
- Each `HistoryEntry` gets a `crypto.randomUUID()` ID and `Date.now()` timestamp.
- Clicking a history item restores the cached SPARQL + rows — no backend call.
- The history overlay is opened via the `≡ ιστορικό (n)` button in the header.

## Accessibility

- All interactive elements have `aria-label` or `aria-expanded`.
- Error banner has `role="alert"`.
- Sort headers have `aria-sort`.
- History items have `role="button"` and `tabIndex={0}` with keyboard handlers.
- All animations respect `prefers-reduced-motion: reduce`.

## Design tokens (styles.css)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#fbf9f4` (parchment) | `#1a1410` | Page background |
| `--ink` | `#1a1410` | `#fbf9f4` | Text, all borders |
| `--accent` | `#7c2d12` (burnt orange) | `#ea580c` | Active states, `//` status labels |
| `--success` | `#14532d` (forest green) | `#22c55e` | Live dot, result count-up |
| `--font-mono` | `JetBrains Mono, Fira Code` | same | Headings, labels, code, buttons |
| `--font-body` | `Inter, system-ui` | same | Greek body text, table cells |

All corners are sharp (`border-radius: 0`). Hover pattern: background→`--ink`, color→`--bg`.

## What NOT to do

- Don't use `EventSource` for SSE — backend uses POST; use `fetch + ReadableStream`
- Don't parse or transform SPARQL — display-only; show what the backend returns
- Don't hardcode Greek strings in components — add to `i18n/el.ts` and use `t.key`
- Don't call GraphDB from the frontend — backend handles it; frontend never touches the endpoint
- Don't inline SPARQL strings — display what the backend returns
- Don't skip `pnpm typecheck` before committing
- Don't sort column values independently — always sort the `rows` array as whole objects (row-coherent)
- Don't call the backend directly from components — use `submit()` from `useQueryStream`
