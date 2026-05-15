# Frontend Guide — evdo-nlq

A beginner-friendly walkthrough of every file in `frontend/src/`. Read this before touching any code.

---

## What the app does

A user types a question in Greek (or English) about Greek university textbooks. The frontend sends that question to a Python backend, which asks an LLM (Claude or Gemini) to turn it into a SPARQL query. The SPARQL streams back one token at a time (like a typewriter), then the backend runs it against a GraphDB database and sends back the results. The frontend shows everything: the query while it's being written, a loading indicator while the database runs, and then the results in a paginated sortable table.

```
User types question
       ↓
QueryForm sends it to useQueryStream
       ↓
useQueryStream opens an SSE stream to POST /query/stream
       ↓
SPARQL tokens arrive one-by-one → SparqlPanel shows them live
       ↓
GraphDB executes the SPARQL → results arrive
       ↓
ResultsTable shows rows, pagination, sort, export
       ↓
Entry saved to history sidebar (localStorage)
```

---

## How to run the app

There are three ways, each useful for different situations:

### 1. Full pipeline (real LLM + real database)
```powershell
# Terminal 1 — start the backend
cd backend
uv run fastapi dev app/main.py

# Terminal 2 — start the frontend
cd frontend
pnpm dev
```
Open http://localhost:5173. Requires API keys in `backend/.env`.

### 2. Mock mode (no backend, no API keys)
```powershell
cd frontend
$env:VITE_USE_MOCK_API='1'
pnpm dev
```
Uses a canned response hardcoded in `api/mock.ts`. Great for working on CSS, layout, or component logic without spending tokens.

### 3. Typecheck only
```powershell
cd frontend
pnpm typecheck
```
Run this before every commit. It catches TypeScript errors without starting a server.

---

## Folder structure

```
frontend/
├── package.json          — project scripts and dependencies
├── vite.config.ts        — dev-server proxy rules
└── src/
    ├── main.tsx           — entry point, mounts <App/>
    ├── App.tsx            — top-level layout and state wiring
    ├── types.ts           — shared TypeScript types
    ├── styles.css         — all CSS (design tokens, animations, layout)
    ├── vite-env.d.ts      — tells TypeScript about Vite env variables
    │
    ├── api/
    │   ├── client.ts      — SSE stream parser (reads from backend)
    │   └── mock.ts        — fake backend for UI development
    │
    ├── hooks/
    │   ├── useQueryStream.ts  — main state machine for a query lifecycle
    │   ├── useHistory.ts      — localStorage query history (20-item cap)
    │   └── useSortedPaged.ts  — sorting + pagination logic for the table
    │
    ├── i18n/
    │   └── el.ts          — every Greek string shown in the UI
    │
    ├── utils/
    │   └── exporters.ts   — CSV / JSON / XML / TSV download helpers
    │
    └── components/
        ├── QueryForm.tsx       — search input, provider/model selectors, submit
        ├── SparqlPanel.tsx     — streaming SPARQL display with copy + collapse
        ├── ErrorBanner.tsx     — dismissable error message
        ├── HistorySidebar.tsx  — overlay list of past queries
        ├── SortIcon.tsx        — the ↕ / A↑Z / Z↑A sort indicator SVG
        └── ResultsTable/
            ├── ResultsTable.tsx  — orchestrator: owns sort, page, column state
            ├── Pagination.tsx    — prev/next buttons and page-size selector
            ├── ColumnsMenu.tsx   — checkbox dropdown to show/hide columns
            ├── ExportMenu.tsx    — dropdown to download CSV/JSON/XML/TSV
            └── EmptyState.tsx    — "0 results" block with clickable suggestions
```

---

## `types.ts` — the shared vocabulary

Read this file first. It defines all the types the rest of the app uses.

### `QueryState` — the most important type

The entire UI is driven by this discriminated union. At any moment the app is in exactly one of four states:

```typescript
type QueryState =
  | { status: 'idle' }                    // nothing has happened yet
  | { status: 'streaming'; sparql: string; executing?: boolean; ... }  // query in progress
  | { status: 'done'; sparql: string; columns: string[]; rows: ...; inputTokens: number; ... }
  | { status: 'error'; message: string; sparql?: string }
```

**What each state means:**
- `idle` — blank slate, just the form
- `streaming` — SPARQL is being written by the LLM token-by-token. When `executing: true`, the SPARQL is done but GraphDB is still running it.
- `done` — everything finished. Results are available.
- `error` — something went wrong. `sparql` might still be set if the query was generated before the error.

### `HistoryEntry`

Saved to localStorage when a query completes. Contains everything needed to replay the result without hitting the database again: the question, the SPARQL, the columns, the rows, token counts.

### `SortState` and `ColumnVisibility`

Used by the results table to track which column is sorted (and in which direction), and which columns are currently visible.

---

## `hooks/useQueryStream.ts` — the brain of the app

This is the most important file after `types.ts`. It manages the entire lifecycle of a query using React's `useReducer`.

### The state machine

```
         submit()
idle  ──────────────► streaming
                          │
                          │  SPARQL tokens arrive (TOKEN actions)
                          │  sparql field grows character by character
                          │
                          │  sparql_complete event
                          │  → executing = true (GraphDB is running)
                          │
                          │  results event
                          │  → executing = false (rows stored temporarily)
                          │
              ┌───────────┴────────────┐
           DONE event              ERROR event
              │                        │
              ▼                        ▼
            done                     error
              │                        │
           clear()               dismissError()
              └───────────┬────────────┘
                          ▼
                        idle
```

### How the reducer works

Every SSE event from the backend dispatches an action:

| Backend event | Action dispatched | What changes |
|---|---|---|
| (submit button clicked) | `SUBMIT` | → `streaming`, sparql = `''` |
| `sparql_token` | `TOKEN` | appends one character to `sparql` |
| `sparql_complete` | `COMPLETE` | replaces `sparql` with clean final version, sets `executing: true` |
| `results` | `RESULTS` | stores `columns` and `rows` in streaming state |
| `done` | `DONE` | → `done` state with tokens counts |
| `error` | `ERROR` | → `error` state |

### What the hook returns

```typescript
const { state, providers, submit, dismissError, clear } = useQueryStream()
```

- `state` — the current `QueryState`
- `providers` — list of available LLM providers fetched from `GET /providers` on mount
- `submit(question, provider, model)` — starts a new query. Aborts any in-flight request first.
- `dismissError()` — goes from `error` back to `idle`
- `clear()` — aborts any request and goes back to `idle` from any state

### Abort behaviour

Every call to `submit()` creates a new `AbortController`. If the user submits a new question while a previous one is streaming, the old request is immediately aborted (the backend SSE connection is dropped) and a fresh one starts. This prevents stale results from arriving and corrupting the state.

---

## `api/client.ts` — the SSE parser

### Why not `EventSource`?

The browser's built-in `EventSource` API only supports `GET` requests. The backend needs the question and provider selection in the request body, which requires `POST`. So instead the app uses `fetch()` with `ReadableStream` to manually parse the SSE wire format.

### What SSE looks like on the wire

```
event: sparql_token\r\n
data: PREFIX\r\n
\r\n
event: sparql_token\r\n
data:  evdx\r\n
\r\n
```

The backend library (`sse_starlette`) uses `\r\n` line endings and `\r\n\r\n` event separators. The parser normalises `\r\n` to `\n` immediately after each `reader.read()` call so that `\n\n` reliably marks event boundaries.

### Step-by-step

1. `fetch('/query/stream', { method: 'POST', body: JSON.stringify({question, provider, model}) })`
2. Get `response.body` as a `ReadableStream<Uint8Array>`
3. Use a `TextDecoder` to convert binary chunks to strings
4. Accumulate text in a `buffer`, normalise `\r\n → \n`
5. Split on `\n\n` to get complete events
6. Parse each event's `event:` and `data:` lines
7. `yield` a `ParsedSSEEvent` for each complete event
8. The caller (`useQueryStream`) iterates with `for await ... of` and dispatches reducer actions

### Mock mode

When `VITE_USE_MOCK_API=1` is set at dev-server startup, `client.ts` delegates to `api/mock.ts` instead of making a real network request. The mock module is loaded via a **dynamic import** (`await import('./mock')`) so it is never included in production bundles — no dead code ships. The mock yields the same `ParsedSSEEvent` objects that the real parser would, but generates them from hardcoded data with artificial delays (18ms per SPARQL character, 300ms for "GraphDB executing").

### Stream cleanup

`client.ts` has a `finally` block that always calls `reader.releaseLock()`. This is important: if the `AbortSignal` fires mid-stream, `fetch` throws and JavaScript skips to `finally`, ensuring the `ReadableStream` lock is always released and no resource leaks occur.

---

## `api/mock.ts` — the fake backend

Contains two exports:

- `MOCK_RESULTS` — a hardcoded object with `columns` and `rows` representing 46 Greek universities. This is the data the mock "returns" after the fake SPARQL completes.
- `mockStreamQuery()` — an async generator that:
  1. Yields `sparql_token` events one character at a time (18ms delay each) to simulate the LLM typewriter effect
  2. Yields `sparql_complete` with the full SPARQL string
  3. Waits 300ms (simulating GraphDB execution)
  4. Yields a `results` event with `MOCK_RESULTS`
  5. Yields a `done` event

This lets you develop and test the entire UI (animations, streaming cursor, pagination, sort, export) without any API keys or a running backend.

---

## `App.tsx` — the layout and wiring

`App` is the component that connects everything. It:

1. Calls `useQueryStream()` and `useHistory()` to get state and actions
2. Manages UI-level state: `theme`, `historyOpen`, `cachedResult`, `prefillQuestion`
3. Renders the **history overlay**, **header**, **query form**, **SPARQL panel**, **results table** or **error banner**

### What gets rendered in each state

| `state.status` | What's visible |
|---|---|
| `idle` | Header + QueryForm only |
| `streaming` | Header + QueryForm (disabled) + SparqlPanel (live cursor) + GraphDB bar |
| `done` | Header + QueryForm + SparqlPanel (collapsed by default) + ResultsTable |
| `error` | Header + QueryForm + SparqlPanel (if SPARQL was generated) + ErrorBanner |

### Cached history view

When the user clicks a history item, `cachedResult` is set in App. The app then displays the cached SPARQL and results instead of the live query state. The `(αποθηκευμένο)` badge appears on the results panel. Submitting a new query clears `cachedResult`.

### Key state variables

| Variable | Purpose |
|---|---|
| `submissionCount` | Used as a React `key` on `<SparqlPanel>` to force-remount it (reset collapsed state) on each new query |
| `prefillQuestion` | Passed to `QueryForm` to sync the input when an example suggestion or history item is clicked |
| `historyOpen` | Whether the history overlay is visible |
| `activeHistoryId` | Which history entry is highlighted |
| `lastMeta` | The provider/model used in the last query, so example clicks reuse the same model |

---

## `components/QueryForm.tsx`

Renders the search input, provider/model dropdowns, the submit button, and the optional clear button.

- The `›` prefix on the input is **decorative only** — it does not mean anything to the backend.
- Provider and model selects are **native `<select>` elements** — this is intentional for accessibility (screen readers, keyboard navigation, mobile).
- When `prefillQuestion` prop changes (e.g., user clicks a history item), a `useEffect` updates the local `question` state, so the input reflects what's being displayed.
- The clear button (`✕ εκκαθάριση`) only appears when there is something to clear (`showClear` prop).

---

## `components/SparqlPanel.tsx`

Shows the SPARQL query while it's being generated and after it's complete.

- While `streaming: true`, a blinking cursor `▌` is appended to the code block.
- Status text switches between `// generating…` and `// ready`.
- The **copy button** uses `navigator.clipboard.writeText()` and shows `✓ αντιγράφηκε` for 1.5 seconds.
- The **collapse button** toggles local `collapsed` state — this is not lifted to App because it only matters inside this component.
- The **GraphDB executing bar** appears when `executing` prop is true (between `sparql_complete` and `results` events) — it shows an animated orange sweep.
- `white-space: pre-wrap` on the code block means long lines (like `NOT_ANSWERABLE` comments) wrap instead of causing horizontal scroll.

---

## `components/HistorySidebar.tsx`

An overlay panel showing past queries. Opens from a button in the header; clicking the backdrop closes it.

- **Persistence**: `useHistory` reads/writes `localStorage` key `evdograph.history`. Entries survive page reloads.
- **Cap**: Maximum 20 entries. Oldest entries are dropped first (FIFO).
- **Each entry** shows: timestamp, row count (or `σφάλμα` for errors), and the NL question (truncated at 2 lines).
- **Active entry**: the currently displayed query gets a 3px burnt-orange left border.
- **Search**: filters entries by substring of the NL question, client-side only.
- **Clicking an entry**: loads the cached SPARQL + results without hitting the backend. The input also updates to reflect the cached question.

---

## `hooks/useHistory.ts`

Manages the 20-item localStorage history.

```typescript
const { entries, addEntry, clearHistory } = useHistory()
```

- `entries` — array of `HistoryEntry`, newest first
- `addEntry(input)` — prepends a new entry, caps at 20, saves to localStorage
- `clearHistory()` — empties the array and removes the localStorage key

Every `HistoryEntry` is given a UUID (`crypto.randomUUID()`) and a timestamp (`Date.now()`) on creation.

---

## `components/ResultsTable/` — the results section

The results table is split into several focused components. `ResultsTable.tsx` is the orchestrator — it owns all the state and passes data down.

### State owned by `ResultsTable`

| State | What it does |
|---|---|
| `sortState` | Which column is sorted and in which direction (`idle / asc / desc`) |
| `pageIndex` | Which page is currently shown (0-indexed) |
| `pageSize` | How many rows per page (10 / 25 / 50 / 100, default 10) |
| `visibility` | Which columns are shown (`Record<string, boolean>`) |
| `showColumns` | Whether the columns dropdown is open |
| `showExport` | Whether the export dropdown is open |

All of this state **resets** when the `columns` prop changes (i.e., on each new query). Column visibility also resets on each query — this is intentional.

### `hooks/useSortedPaged.ts`

A pure memoised hook that takes `(rows, sortState, pageSize, pageIndex)` and returns `{ visibleRows, totalPages }`.

The sort comparator is **numeric-aware**: if all values in a column look like numbers, it sorts numerically. Otherwise it uses `localeCompare` with Greek locale settings. Sorting is **row-coherent** — the entire row object moves, never individual column values.

### `components/SortIcon.tsx`

A small inline SVG rendered as one of three states:
- `idle` — dim sand double-chevron (⇅) — mirrors `public/dafaultIndicator.png`
- `asc` — burnt-orange A↑Z — mirrors `public/indicator1.png`
- `desc` — burnt-orange Z↑A — mirrors `public/indicator2.png`

SVG is used instead of the PNG images so the icon colour respects CSS variables (works in both light and dark themes).

### `components/ResultsTable/Pagination.tsx`

Renders the row-count selector and page navigation. Clicking a page number calls `onPageChange`. Changing the page size calls `onPageSizeChange` and resets the page to 0.

### `components/ResultsTable/ColumnsMenu.tsx`

A dropdown with a checkbox per column. Clicking a column toggles its visibility. The parent (`ResultsTable`) handles the state. The checkbox is a styled `<div>` with `role="menuitemcheckbox"` for accessibility.

### `components/ResultsTable/ExportMenu.tsx`

A dropdown with four options: CSV, JSON, XML, TSV. Clicking any option calls the matching serialiser in `utils/exporters.ts` with **all rows** (not just the current page) and triggers a browser download.

### `components/ResultsTable/EmptyState.tsx`

Shown when a query returns zero rows. Displays `// 0 αποτελέσματα` and three clickable example questions. Clicking an example calls `onExampleSelect(question)`, which goes up to App, which pre-fills the input and submits.

---

## `utils/exporters.ts` — download helpers

Four pure functions that take `(columns, rows)` and return a string:

| Function | Format | Notes |
|---|---|---|
| `toCSV` | Comma-separated, RFC 4180 | Values with commas/quotes/newlines are double-quoted |
| `toJSON` | JSON array of objects | 2-space indented |
| `toXML` | SPARQL results XML | Standard W3C format, useful for SPARQL tooling |
| `toTSV` | Tab-separated | Tabs inside values are replaced with spaces |

`downloadBlob(content, ext)` creates a `Blob`, attaches it to an invisible `<a>` tag, clicks it programmatically, then removes the tag. The filename is always `evdograph-results-YYYY-MM-DD-HHmmss.{ext}`.

---

## `i18n/el.ts` — all Greek strings

Every piece of text shown in the UI lives in this single object. No component has hardcoded Greek strings.

Usage pattern in components:
```typescript
import { t } from '../i18n/el'
// ...
<button>{t.searchButton}</button>  // renders "ΑΝΑΖΗΤΗΣΗ →"
```

Some keys are functions:
```typescript
t.pageInfo(2, 5)        // → "σελίδα 2 από 5"
t.historyMobileToggle(3) // → "≡ ιστορικό (3)"
```

To add a new UI string, add a key to `el.ts` and import `t` where you need it.

---

## `styles.css` — the design system

### CSS variables (design tokens)

All colours, fonts, and spacing are defined as CSS custom properties at the top of the file. Light theme is the default; dark theme overrides are in `[data-theme="dark"]`.

| Variable | Light | Dark | Used for |
|---|---|---|---|
| `--bg` | `#fbf9f4` (parchment) | `#1a1410` (ink) | Page background |
| `--panel` | `#fbf9f4` | `#1a1410` | Panel backgrounds |
| `--ink` | `#1a1410` | `#fbf9f4` | Text, borders |
| `--ink-soft` | `#8a7860` | `#a89478` | Muted text, timestamps |
| `--accent` | `#7c2d12` (burnt orange) | `#ea580c` | Active states, `//` labels |
| `--success` | `#14532d` (forest green) | `#22c55e` | Live dot, result count |
| `--code-bg` | `#ffffff` | `#0d0a08` | SPARQL code block |

### Typography rule

- **Monospace** (`JetBrains Mono`): headings, labels, code, status lines, anything in the CLI/terminal family
- **System sans-serif** (`Inter`): Greek body text in table cells, error messages, long prose — mono renders Greek awkwardly in running text

### Animations

| Keyframe | Where used | What it does |
|---|---|---|
| `livepulse` | `.live-dot` | Green square pulses opacity + scale |
| `blink` | `.cursor` | SPARQL streaming cursor blinks on/off |
| `rowin` | `tbody tr` | Each table row fades + slides in with a stagger |
| `countup` | `.results-count` | Result count fades up into view |
| `progressmove` | `.graphdb-sweep` | Orange bar slides across the GraphDB indicator |

All animations respect `prefers-reduced-motion: reduce` — they are disabled for users who have that setting.

---

## `vite.config.ts` — the dev-server proxy

```typescript
server: {
  proxy: {
    '/query':     'http://localhost:8000',
    '/providers': 'http://localhost:8000',
  },
}
```

This means `fetch('/query/stream', ...)` in the browser actually hits `http://localhost:8000/query/stream` on the backend. Without this proxy the browser would get a CORS error. In production a real reverse proxy (nginx, Caddy) would handle this.

---

## `main.tsx` — the entry point

Nothing interesting here. It mounts `<App/>` inside `React.StrictMode` (which runs effects twice in development to catch bugs) into the `#root` div in `index.html`.

---

## How to add a new feature — a quick guide

### Add a new UI string
1. Open `i18n/el.ts` and add a key: `myLabel: 'Ελληνικό κείμενο'`
2. Import and use `t.myLabel` in your component

### Add a new results table column interaction (e.g., column resize)
1. Add state to `ResultsTable.tsx`
2. Pass it down to `TableHeader` or a new component
3. If it needs to persist, add it to `HistoryEntry` in `types.ts` and save it in `useHistory`

### Add a new export format (e.g., Parquet)
1. Add a `toParquet()` function in `utils/exporters.ts`
2. Add a `'parquet'` case to `downloadBlob`'s `mimeTypes` map
3. Add an entry to the `FORMATS` array in `ExportMenu.tsx`
4. Add the label to `i18n/el.ts`

### Add a new LLM provider to the dropdown
The provider list comes from `GET /providers` on the backend — no frontend change needed. The backend `providers.py` is the only place to update.

### Test without spending LLM tokens
```powershell
$env:VITE_USE_MOCK_API='1'
pnpm dev
```
The mock in `api/mock.ts` covers: streaming cursor, GraphDB indicator, pagination (44 rows), sort, export. It does not cover errors or retries — test those with the real backend + `LLM_PROVIDER=fake`.

---

## Common beginner mistakes

| Mistake | Why it's wrong | What to do instead |
|---|---|---|
| Adding hardcoded Greek text to a component | Breaks the i18n pattern | Add to `i18n/el.ts`, use `t.yourKey` |
| Parsing or transforming the SPARQL string | Frontend is display-only | Show exactly what the backend returns |
| Calling `GET /providers` or `POST /query` directly with `fetch` | Bypasses the SSE parser | Use `submit()` from `useQueryStream` |
| Making the table sort per-column independently | Scrambles row data | Always sort the `rows` array as whole objects |
| Sorting/filtering inside a component's render | Recalculates every render | Use `useSortedPaged` with `useMemo` |
| Using `EventSource` for SSE | Only supports GET | Use `fetch + ReadableStream` via `client.ts` |
| Hardcoding the GraphDB endpoint in the frontend | Security + CORS | Backend handles it; frontend never talks to GraphDB |
