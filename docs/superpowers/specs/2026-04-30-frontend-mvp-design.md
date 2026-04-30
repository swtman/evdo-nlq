# Frontend MVP Design

**Date:** 2026-04-30  
**Status:** Approved  
**Goal:** A React + Vite + TypeScript SPA that lets users ask natural-language questions in Greek, watch SPARQL stream live from the LLM, and see GraphDB results in a table.

---

## Decisions

| Decision | Choice |
|---|---|
| Stack | React 18 + TypeScript + Vite + plain CSS |
| Layout | Single column (form → SPARQL panel → results table) |
| Visual style | Dark (`#111827`) + emerald accent on SPARQL (`#10b981`) + blue accent on results (`#3b82f6`) |
| State management | `useQueryStream` custom hook (Option B) — components are purely presentational |
| Streaming | `fetch + ReadableStream` on `POST /query/stream` — NOT `EventSource` (backend uses POST) |
| Provider selection | Dropdown populated from `GET /providers` at mount |
| Dev without tokens | `VITE_USE_MOCK_API=1` returns canned SSE events from `api/mock.ts` |
| Language | All UI strings in `src/i18n/el.ts` (Greek) |
| Tests | None for MVP — `pnpm typecheck` is the gate |

---

## Architecture

```
frontend/src/
├── main.tsx                  mounts <App />
├── App.tsx                   layout shell; wires hook → components
├── styles.css                dark theme, CSS custom properties
├── types.ts                  Provider, QueryResult, QueryState (discriminated union)
├── api/
│   ├── client.ts             ReadableStream SSE parser → AsyncIterable<ParsedEvent>
│   └── mock.ts               canned events for VITE_USE_MOCK_API=1
├── hooks/
│   └── useQueryStream.ts     SSE state machine + AbortController cleanup
├── components/
│   ├── QueryForm.tsx         question input + provider/model dropdowns + submit
│   ├── SparqlPanel.tsx       live SPARQL, collapsible, blinking cursor, emerald accent
│   ├── ResultsTable.tsx      table + token count footer, blue accent
│   └── ErrorBanner.tsx       dismissible red banner
└── i18n/
    └── el.ts                 all Greek strings as a flat object
```

---

## State machine

```
idle → streaming → done
             ↓
           error
```

`useQueryStream` exposes: `{ state, providers, submit, dismissError }`

`state` is a discriminated union:
- `{ status: 'idle' }`
- `{ status: 'streaming', sparql: string }`
- `{ status: 'done', sparql, columns, rows, inputTokens, outputTokens, retries }`
- `{ status: 'error', message: string }`

---

## SSE events consumed

From `POST /query/stream` (see `backend/app/api/query.py`):

| Event | Payload | Action |
|---|---|---|
| `sparql_token` | token text | Append to `state.sparql` |
| `sparql_complete` | full SPARQL | Finalize SPARQL display |
| `sparql_retry` | `{ attempt, error }` | Log (no UI action for MVP) |
| `results` | `{ columns, rows }` | Store in state |
| `done` | `{ input_tokens, output_tokens, retries }` | Transition to `done` |
| `error` | `{ message }` | Transition to `error` |

---

## Visual style

CSS custom properties:
```css
--bg: #111827;
--panel: #1f2937;
--border: #374151;
--emerald: #10b981;
--blue: #3b82f6;
--text: #f9fafb;
--muted: #6b7280;
```

Logo gradient: `linear-gradient(90deg, #10b981, #3b82f6)` on "NLQ".  
SPARQL panel: `border-left: 3px solid var(--emerald)`.  
Results panel: `border-left: 3px solid var(--blue)`.

---

## Out of scope (deferred)

- Unit/component tests
- English language toggle
- Query history
- Authentication
- Mobile-responsive polish
- SPARQL syntax highlighting
