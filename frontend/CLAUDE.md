# frontend/ — React + Vite UI

Single-page app: natural-language input form → live SPARQL streaming panel → results table, with error handling. MVP complete as of 2026-05-01.

## Stack

- React 18 + TypeScript
- Vite (dev server on :5173, hot reload enabled, build with `pnpm build`)
- Plain CSS (no Tailwind — dark theme with CSS variables)
- `fetch` + `ReadableStream` for SSE (not `EventSource` — backend uses POST)
- Custom `useQueryStream` hook with `useReducer` state machine

## Folder structure

```
src/
├── main.tsx                        entrypoint, mounts App in StrictMode
├── App.tsx                         layout shell, wires hook + components
├── types.ts                        QueryState (discriminated union), Provider, ParsedSSEEvent
├── styles.css                      dark theme, 230+ lines, CSS variables for colors
├── vite-env.d.ts                   Vite env type augmentation (VITE_USE_MOCK_API)
├── components/
│   ├── QueryForm.tsx               input + provider/model dropdowns + submit button
│   ├── SparqlPanel.tsx             collapsible SPARQL display, blinking cursor, emerald accent
│   ├── ResultsTable.tsx            table from { columns, rows }, token footer, blue accent
│   └── ErrorBanner.tsx             dismissible alert, role="alert", accessible dismiss
├── hooks/
│   └── useQueryStream.ts           SSE state machine, AbortController lifecycle, providers fetch
├── api/
│   ├── client.ts                   SSE parser via fetch + ReadableStream, delegates to mock
│   └── mock.ts                     canned SPARQL stream for UI development (char-by-char at 18ms)
└── i18n/
    └── el.ts                       all UI strings in Greek
```

## Commands

```powershell
pnpm dev                  # dev server (hot reload) on http://localhost:5173
pnpm build                # production build (dist/)
pnpm preview              # serve production build locally
pnpm typecheck            # tsc --noEmit (type safety gate — run before every commit)
```

## Running modes

### Mode 1 — Full pipeline (real LLM + real GraphDB)

Needs a running backend with `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY`) in `backend/.env`.

```powershell
# Terminal 1
cd backend; uv run fastapi dev app/main.py

# Terminal 2
cd frontend; pnpm dev
```

Open `http://localhost:5173`. Provider/model dropdown is auto-populated from `GET /providers`. Submit any Greek or English question about university textbooks.

### Mode 2 — Frontend with fake LLM backend (no API key)

Use when you want a real HTTP round-trip (SSE parsing, proxy, error paths) but don't want to spend LLM tokens.

```powershell
# Terminal 1 — backend with fake provider
cd backend
# set LLM_PROVIDER=fake in backend/.env  OR
$env:LLM_PROVIDER='fake'; uv run fastapi dev app/main.py

# Terminal 2
cd frontend; pnpm dev
```

The backend returns a canned SPARQL response and queries GraphDB for real. Provider dropdown will show `fake / fake-v1`.

### Mode 3 — Mock API (no backend at all)

Use for CSS/layout/component iteration. No backend required, no network calls.

```powershell
cd frontend; $env:VITE_USE_MOCK_API='1'; pnpm dev
```

`VITE_USE_MOCK_API=1` makes `client.ts` delegate to `mock.ts`, which streams canned SPARQL character-by-character (typewriter effect) then emits a hard-coded results table. The env var is Vite-specific and only affects the dev build.

## API contract

**Endpoint:** `POST /query/stream` (proxied by Vite to `http://localhost:8000`)

**Request body:**
```json
{ "question": "string", "provider": "string", "model": "string" }
```

**Response:** Server-Sent Events with `event:` and `data:` fields.

| Event | Data | Purpose |
|-------|------|---------|
| `sparql_token` | token text (may include code fences) | Append to `state.sparql` while streaming |
| `sparql_complete` | final cleaned SPARQL string | Replace `state.sparql` with authoritative value |
| `sparql_retry` | `{ attempt, error }` | Informational — not yet surfaced in UI |
| `results` | `{ columns: string[], rows: Record<string, string \| undefined>[] }` | Populate results table |
| `done` | `{ provider, model, input_tokens, output_tokens, retries }` | Show token counts, transition to done |
| `error` | `{ message: string }` | Display ErrorBanner, transition to error state |

### SSE parser note (`api/client.ts`)

`sse_starlette` (the backend SSE library) uses `\r\n` line endings and `\r\n\r\n` event separators — not the `\n\n` that the SSE spec also allows. The parser normalizes `\r\n → \n` immediately after every `reader.read()` call so that `\n\n` reliably marks event boundaries. It also:
- Concatenates multi-line `data:` fields (SPARQL queries may span multiple lines).
- Flushes the remaining buffer when the stream closes, so the final `done` event is never lost.

## State machine (useQueryStream)

```
idle → (submit) → streaming → (done event) → done
                       ↓
                  (error event) → error → (dismiss) → idle
```

The `streaming` state accumulates `columns` and `rows` from the `results` event before `done` arrives. The `DONE` reducer action reads them from the streaming state to build the final `done` state.

The `streaming` state also carries an `executing?: boolean` flag that is set to `true` on `sparql_complete` and cleared on `results`. This drives the GraphDB execution indicator shown between those two events.

The `error` state carries `sparql?: string` — the SPARQL that was being generated when the error occurred — so the SPARQL panel stays visible after a GraphDB failure.

**Hook signature:**
```typescript
const { state, providers, submit, dismissError } = useQueryStream()
```

- `state` — discriminated union `QueryState`: `idle | streaming | done | error`
- `providers` — `Provider[]` from `GET /providers`, loaded on mount
- `submit(question, provider, model)` — fires SSE fetch, aborts any in-flight request first
- `dismissError()` — transitions from `error` back to `idle`

## Accessibility

- All interactive elements have `aria-label` or `aria-expanded`
- Error banner has `role="alert"` for screen reader announcement
- Dismiss button has semantic `type="button"` and accessible label

## i18n

- All visible strings in `src/i18n/el.ts` (Greek primary)
- To add English: create `src/i18n/en.ts` and swap the import in components, or select at runtime
- No hardcoded English anywhere in components

## Theme (light/dark + accent colors)

The app supports light and dark themes. A sun/moon toggle button in the header switches between them; the preference is persisted in `localStorage` and applied via `document.documentElement.dataset.theme`.

CSS variables in `styles.css` (dark defaults, overridden by `[data-theme="light"]`):
- `--bg` — main background (`#111827` dark / `#f1f5f9` light)
- `--panel` — panel backgrounds (`#1f2937` / `#ffffff`)
- `--border` — borders (`#374151` / `#e2e8f0`)
- `--text` — primary text (`#f9fafb` / `#0f172a`)
- `--muted` — secondary text (`#6b7280` / `#64748b`)
- `--code` — SPARQL code color (`#d1fae5` / `#14532d`)
- `--emerald: #10b981` — SPARQL panel accent (same both themes)
- `--blue: #3b82f6` — results panel accent (same both themes)

Logo uses `linear-gradient(90deg, #10b981, #3b82f6)` (emerald → blue).

## What NOT to do

- Don't call LLM APIs from the frontend (backend only)
- Don't parse or transform SPARQL (display-only — show what the backend returns)
- Don't hardcode the GraphDB endpoint (backend handles execution)
- Don't use `EventSource` for SSE (backend uses POST; use `fetch + ReadableStream`)
- Don't split SSE events on `\n\n` without first normalizing `\r\n` — sse_starlette uses CRLF
- Don't skip `pnpm typecheck` before committing
