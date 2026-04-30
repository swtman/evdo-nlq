# Frontend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React + Vite + TypeScript SPA that lets users ask natural-language questions in Greek, watch SPARQL tokens stream live, and see GraphDB results in a table.

**Architecture:** A single `useQueryStream` custom hook owns all SSE fetch logic (fetch + ReadableStream, AbortController cleanup) and a `useReducer` state machine (idle → streaming → done / error). Four presentational components render the state. A `VITE_USE_MOCK_API=1` path in `api/client.ts` returns canned events so the UI can be built and styled without a live backend.

**Tech Stack:** React 18, TypeScript 5, Vite 5, plain CSS (no Tailwind). `pnpm` for package management. No test framework — `pnpm typecheck` (`tsc --noEmit`) is the gate before every commit.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `frontend/package.json` | Vite + React + TS scaffold (via `pnpm create vite`) |
| Create | `frontend/vite.config.ts` | Dev proxy: `/query` + `/providers` → `localhost:8000` |
| Create | `frontend/src/vite-env.d.ts` | Augment `ImportMetaEnv` with `VITE_USE_MOCK_API` |
| Create | `frontend/src/types.ts` | `Provider`, `QueryState` discriminated union, `ParsedSSEEvent` |
| Create | `frontend/src/i18n/el.ts` | All Greek UI strings as a flat `t` object |
| Create | `frontend/src/styles.css` | Full dark theme — CSS custom properties + all component styles |
| Create | `frontend/src/api/client.ts` | `streamQuery()` — real fetch + ReadableStream SSE parser |
| Create | `frontend/src/api/mock.ts` | `mockStreamQuery()` — canned events char-by-char |
| Create | `frontend/src/hooks/useQueryStream.ts` | `useReducer` state machine + `AbortController` + providers fetch |
| Create | `frontend/src/components/QueryForm.tsx` | Question input + provider/model dropdowns + submit |
| Create | `frontend/src/components/SparqlPanel.tsx` | Collapsible SPARQL display, blinking cursor, emerald accent |
| Create | `frontend/src/components/ResultsTable.tsx` | Results table + token count footer, blue accent |
| Create | `frontend/src/components/ErrorBanner.tsx` | Dismissible red error banner |
| Create | `frontend/src/App.tsx` | Layout shell — wires hook to components |
| Create | `frontend/src/main.tsx` | Entry point — mounts `<App />` into `#root` |
| Create | `frontend/index.html` | HTML shell — `<title>EvdoGraph NLQ</title>` |

---

## Task 1: Scaffold Vite + React + TypeScript

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/vite-env.d.ts`

- [ ] **Step 1: Run the Vite scaffold inside the existing `frontend/` directory**

```bash
cd /c/Users/sotir/evdo-nlq/frontend
pnpm create vite@latest . --template react-ts
```

The directory already has `CLAUDE.md` — Vite will ask "Target directory is not empty." Choose **"Ignore files and continue"**. This keeps `CLAUDE.md` and creates all scaffold files alongside it.

- [ ] **Step 2: Install dependencies**

```bash
cd /c/Users/sotir/evdo-nlq/frontend
pnpm install
pnpm add -D @types/node
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 3: Add `typecheck` script to `package.json`**

Open `frontend/package.json`. Add `"typecheck": "tsc --noEmit"` to the `scripts` object:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit"
  }
}
```

- [ ] **Step 4: Update `index.html` title**

Replace the default `<title>` in `frontend/index.html`:

```html
<!doctype html>
<html lang="el">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>EvdoGraph NLQ</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Configure the Vite dev proxy**

Replace `frontend/vite.config.ts` entirely:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/query': 'http://localhost:8000',
      '/providers': 'http://localhost:8000',
    },
  },
})
```

This forwards `/query/stream` and `/providers` to the FastAPI backend in dev mode.

- [ ] **Step 6: Augment `vite-env.d.ts` with `VITE_USE_MOCK_API`**

Replace `frontend/src/vite-env.d.ts`:

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK_API?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 7: Verify the scaffold runs**

```bash
cd /c/Users/sotir/evdo-nlq/frontend
pnpm dev
```

Expected: Vite dev server starts on `http://localhost:5173`. The default React welcome page is visible. Stop the server (`Ctrl+C`).

- [ ] **Step 8: Typecheck the scaffold**

```bash
cd /c/Users/sotir/evdo-nlq/frontend
pnpm typecheck
```

Expected: no errors (or only the default scaffold errors — none from our added files).

- [ ] **Step 9: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/
git -C /c/Users/sotir/evdo-nlq commit -m "feat: scaffold frontend Vite + React + TS"
```

---

## Task 2: Types and Greek strings

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/i18n/el.ts`

- [ ] **Step 1: Create `frontend/src/types.ts`**

```typescript
export type Provider = {
  id: string
  models: string[]
}

export type ParsedSSEEvent = {
  event: string
  data: string
}

export type QueryState =
  | { status: 'idle' }
  | { status: 'streaming'; sparql: string; columns?: string[]; rows?: Record<string, string>[] }
  | {
      status: 'done'
      sparql: string
      columns: string[]
      rows: Record<string, string>[]
      inputTokens: number
      outputTokens: number
      retries: number
    }
  | { status: 'error'; message: string }
```

- [ ] **Step 2: Create `frontend/src/i18n/el.ts`**

```typescript
export const t = {
  title: 'EvdoGraph',
  titleAccent: 'NLQ',
  subtitle: 'Φυσική γλώσσα → SPARQL → Αποτελέσματα',
  searchPlaceholder: 'Ρωτήστε για βιβλία, συγγραφείς, μαθήματα...',
  searchButton: 'Αναζήτηση',
  searching: 'Αναζήτηση...',
  sparqlLabel: 'SPARQL',
  sparqlGenerating: '● generating',
  sparqlComplete: '✓ complete',
  sparqlCollapse: '▼',
  sparqlExpand: '▶',
  resultsLabel: 'Αποτελέσματα',
  noResults: 'Δεν βρέθηκαν αποτελέσματα.',
  tokenInfo: (input: number, output: number, retries: number): string =>
    `${input} input · ${output} output tokens${retries > 0 ? ` · ${retries} retries` : ''}`,
  errorPrefix: 'Σφάλμα:',
  errorDismiss: '✕',
  providerLabel: 'Πάροχος',
  modelLabel: 'Μοντέλο',
}
```

- [ ] **Step 3: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/types.ts frontend/src/i18n/el.ts
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add TypeScript types and Greek i18n strings"
```

---

## Task 3: CSS dark theme

**Files:**
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Create `frontend/src/styles.css`**

```css
:root {
  --bg: #111827;
  --panel: #1f2937;
  --border: #374151;
  --emerald: #10b981;
  --blue: #3b82f6;
  --red: #ef4444;
  --text: #f9fafb;
  --muted: #6b7280;
  --code: #d1fae5;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, sans-serif;
  min-height: 100vh;
}

/* ---- Layout ---- */
.app {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin: 0 auto;
  max-width: 860px;
  padding: 32px 16px 64px;
}

.app-header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 24px;
  text-align: center;
}

.app-header h1 {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.app-header h1 .accent {
  background: linear-gradient(90deg, #10b981, #3b82f6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.app-header p {
  color: var(--muted);
  font-size: 13px;
  margin-top: 4px;
}

/* ---- Panel ---- */
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
}

.panel--emerald { border-left: 3px solid var(--emerald); }
.panel--blue    { border-left: 3px solid var(--blue); }
.panel--red     { background: #1f1315; border-left: 3px solid var(--red); }

.panel-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}

.panel-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.panel-label--emerald { color: var(--emerald); }
.panel-label--blue    { color: var(--blue); }

/* ---- Status pill ---- */
.status-pill {
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
}

.status-pill--generating { background: #1a3a5c; color: #60a5fa; }
.status-pill--complete   { background: #14322a; color: #34d399; }

/* ---- Query form ---- */
.query-form { display: flex; flex-direction: column; gap: 10px; }

.query-input {
  background: var(--bg);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 15px;
  outline: none;
  padding: 10px 14px;
  transition: border-color 0.15s;
  width: 100%;
}

.query-input::placeholder { color: var(--muted); }
.query-input:focus         { border-color: var(--emerald); }
.query-input:disabled      { cursor: not-allowed; opacity: 0.6; }

.query-controls { align-items: center; display: flex; gap: 8px; }

.query-select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  padding: 6px 10px;
}

.query-select:disabled { cursor: not-allowed; opacity: 0.5; }

.query-button {
  background: linear-gradient(135deg, #10b981, #059669);
  border: none;
  border-radius: 8px;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  margin-left: auto;
  padding: 7px 20px;
  transition: opacity 0.15s;
}

.query-button:disabled { cursor: not-allowed; opacity: 0.5; }
.query-button:not(:disabled):hover { opacity: 0.9; }

/* ---- SPARQL panel ---- */
.sparql-header-left { align-items: center; display: flex; gap: 8px; }

.sparql-code {
  background: var(--bg);
  border-radius: 6px;
  color: var(--code);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  overflow-x: auto;
  padding: 12px 14px;
  white-space: pre;
}

.cursor {
  animation: blink 0.8s step-end infinite;
  color: var(--emerald);
}

@keyframes blink { 50% { opacity: 0; } }

.collapse-btn {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
}

.collapse-btn:hover { color: var(--text); }

/* ---- Results table ---- */
.table-wrapper { overflow-x: auto; }

.results-table {
  border-collapse: collapse;
  font-size: 13px;
  width: 100%;
}

.results-table th {
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  padding: 8px 12px;
  text-align: left;
  text-transform: uppercase;
}

.results-table td {
  border-bottom: 1px solid #1a2535;
  color: var(--text);
  padding: 8px 12px;
}

.results-table tr:last-child td { border-bottom: none; }

.no-results { color: var(--muted); font-size: 13px; padding: 8px 0; }
.token-info { color: var(--muted); font-size: 11px; margin-top: 10px; }

/* ---- Error banner ---- */
.error-banner {
  align-items: center;
  display: flex;
  font-size: 13px;
  justify-content: space-between;
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 4px;
}

.dismiss-btn:hover { color: var(--text); }
```

- [ ] **Step 2: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/styles.css
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add dark theme CSS (emerald/blue accent)"
```

---

## Task 4: API layer — real SSE client + mock

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/mock.ts`

- [ ] **Step 1: Create `frontend/src/api/mock.ts`**

```typescript
import type { ParsedSSEEvent } from '../types'

const MOCK_SPARQL = `PREFIX evdx: <http://evdoxus.csd.auth.gr/ontology#>
SELECT ?title ?author WHERE {
  ?book a evdx:Book ;
        evdx:title ?title ;
        evdx:hasAuthor ?author .
}
LIMIT 10`

const MOCK_RESULTS = {
  columns: ['title', 'author'],
  rows: [
    { title: 'Εισαγωγή στον Προγραμματισμό', author: 'Παπαδόπουλος Γ.' },
    { title: 'Αλγόριθμοι και Δομές Δεδομένων', author: 'Κωνσταντίνου Α.' },
    { title: 'Βάσεις Δεδομένων', author: 'Πέτρου Μ.' },
  ],
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

export async function* mockStreamQuery(
  _question: string,
  provider: string,
  model: string,
  signal: AbortSignal
): AsyncGenerator<ParsedSSEEvent> {
  for (const char of MOCK_SPARQL) {
    await delay(18, signal)
    yield { event: 'sparql_token', data: char }
  }
  yield { event: 'sparql_complete', data: MOCK_SPARQL }
  await delay(300, signal)
  yield { event: 'results', data: JSON.stringify(MOCK_RESULTS) }
  await delay(50, signal)
  yield {
    event: 'done',
    data: JSON.stringify({ provider, model, input_tokens: 120, output_tokens: 45, retries: 0 }),
  }
}
```

- [ ] **Step 2: Create `frontend/src/api/client.ts`**

```typescript
import type { ParsedSSEEvent } from '../types'

export async function* streamQuery(
  question: string,
  provider: string,
  model: string,
  signal: AbortSignal
): AsyncGenerator<ParsedSSEEvent> {
  if (import.meta.env.VITE_USE_MOCK_API === '1') {
    const { mockStreamQuery } = await import('./mock')
    yield* mockStreamQuery(question, provider, model, signal)
    return
  }

  const response = await fetch('/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, provider, model }),
    signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        if (!part.trim()) continue
        let event = ''
        let data = ''
        for (const line of part.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7).trim()
          else if (line.startsWith('data: ')) data = line.slice(6).trim()
        }
        if (event && data) yield { event, data }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
```

- [ ] **Step 3: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/api/
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add SSE client and mock API"
```

---

## Task 5: `useQueryStream` hook

**Files:**
- Create: `frontend/src/hooks/useQueryStream.ts`

- [ ] **Step 1: Create `frontend/src/hooks/useQueryStream.ts`**

```typescript
import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { streamQuery } from '../api/client'
import type { Provider, QueryState } from '../types'

type Action =
  | { type: 'SUBMIT' }
  | { type: 'TOKEN'; payload: string }
  | { type: 'COMPLETE'; payload: string }
  | { type: 'RESULTS'; payload: { columns: string[]; rows: Record<string, string>[] } }
  | { type: 'DONE'; payload: { inputTokens: number; outputTokens: number; retries: number } }
  | { type: 'ERROR'; payload: string }
  | { type: 'DISMISS_ERROR' }

function reducer(state: QueryState, action: Action): QueryState {
  switch (action.type) {
    case 'SUBMIT':
      return { status: 'streaming', sparql: '' }
    case 'TOKEN':
      if (state.status !== 'streaming') return state
      return { ...state, sparql: state.sparql + action.payload }
    case 'COMPLETE':
      if (state.status !== 'streaming') return state
      return { ...state, sparql: action.payload }
    case 'RESULTS':
      if (state.status !== 'streaming') return state
      return { ...state, columns: action.payload.columns, rows: action.payload.rows }
    case 'DONE':
      if (state.status !== 'streaming') return state
      return {
        status: 'done',
        sparql: state.sparql,
        columns: state.columns ?? [],
        rows: state.rows ?? [],
        inputTokens: action.payload.inputTokens,
        outputTokens: action.payload.outputTokens,
        retries: action.payload.retries,
      }
    case 'ERROR':
      return { status: 'error', message: action.payload }
    case 'DISMISS_ERROR':
      return { status: 'idle' }
    default:
      return state
  }
}

export function useQueryStream() {
  const [state, dispatch] = useReducer(reducer, { status: 'idle' })
  const [providers, setProviders] = useState<Provider[]>([])
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let cancelled = false

    if (import.meta.env.VITE_USE_MOCK_API === '1') {
      setProviders([
        { id: 'claude', models: ['claude-haiku-4-5', 'claude-sonnet-4-6'] },
        { id: 'gemini', models: ['gemini-2.0-flash', 'gemini-1.5-flash'] },
        { id: 'fake', models: ['fake-v1'] },
      ])
    } else {
      fetch('/providers')
        .then(r => r.json())
        .then((data: { providers: Provider[] }) => {
          if (!cancelled) setProviders(data.providers ?? [])
        })
        .catch(console.error)
    }

    return () => {
      cancelled = true
      abortRef.current?.abort()
    }
  }, [])

  const submit = useCallback((question: string, provider: string, model: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    dispatch({ type: 'SUBMIT' })

    void (async () => {
      try {
        for await (const { event, data } of streamQuery(question, provider, model, controller.signal)) {
          switch (event) {
            case 'sparql_token':
              dispatch({ type: 'TOKEN', payload: data })
              break
            case 'sparql_complete':
              dispatch({ type: 'COMPLETE', payload: data })
              break
            case 'results': {
              const parsed = JSON.parse(data) as { columns: string[]; rows: Record<string, string>[] }
              dispatch({ type: 'RESULTS', payload: parsed })
              break
            }
            case 'done': {
              const parsed = JSON.parse(data) as { input_tokens: number; output_tokens: number; retries: number }
              dispatch({ type: 'DONE', payload: { inputTokens: parsed.input_tokens, outputTokens: parsed.output_tokens, retries: parsed.retries } })
              break
            }
            case 'error': {
              const parsed = JSON.parse(data) as { message: string }
              dispatch({ type: 'ERROR', payload: parsed.message })
              break
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          dispatch({ type: 'ERROR', payload: err.message })
        }
      }
    })()
  }, [])

  const dismissError = useCallback(() => dispatch({ type: 'DISMISS_ERROR' }), [])

  return { state, providers, submit, dismissError }
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/hooks/useQueryStream.ts
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add useQueryStream hook with SSE state machine"
```

---

## Task 6: `QueryForm` component

**Files:**
- Create: `frontend/src/components/QueryForm.tsx`

- [ ] **Step 1: Create `frontend/src/components/QueryForm.tsx`**

```tsx
import { useState, type FormEvent } from 'react'
import { t } from '../i18n/el'
import type { Provider } from '../types'

type Props = {
  providers: Provider[]
  disabled: boolean
  onSubmit: (question: string, provider: string, model: string) => void
}

export function QueryForm({ providers, disabled, onSubmit }: Props) {
  const [question, setQuestion] = useState('')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModel, setSelectedModel] = useState('')

  const currentProvider = providers.find(p => p.id === (selectedProvider || providers[0]?.id))
  const models = currentProvider?.models ?? []

  const handleProviderChange = (id: string) => {
    setSelectedProvider(id)
    const p = providers.find(pr => pr.id === id)
    setSelectedModel(p?.models[0] ?? '')
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!question.trim() || providers.length === 0) return
    const provider = selectedProvider || providers[0].id
    const model = selectedModel || models[0] || ''
    onSubmit(question.trim(), provider, model)
  }

  return (
    <form className="panel query-form" onSubmit={handleSubmit}>
      <input
        className="query-input"
        type="text"
        value={question}
        onChange={e => setQuestion(e.target.value)}
        placeholder={t.searchPlaceholder}
        disabled={disabled}
        autoFocus
      />
      <div className="query-controls">
        <select
          className="query-select"
          value={selectedProvider || providers[0]?.id || ''}
          onChange={e => handleProviderChange(e.target.value)}
          disabled={disabled || providers.length === 0}
          aria-label={t.providerLabel}
        >
          {providers.map(p => (
            <option key={p.id} value={p.id}>{p.id}</option>
          ))}
        </select>
        <select
          className="query-select"
          value={selectedModel || models[0] || ''}
          onChange={e => setSelectedModel(e.target.value)}
          disabled={disabled || models.length === 0}
          aria-label={t.modelLabel}
        >
          {models.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <button
          type="submit"
          className="query-button"
          disabled={disabled || !question.trim()}
        >
          {disabled ? t.searching : t.searchButton}
        </button>
      </div>
    </form>
  )
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/components/QueryForm.tsx
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add QueryForm component"
```

---

## Task 7: `SparqlPanel` component

**Files:**
- Create: `frontend/src/components/SparqlPanel.tsx`

- [ ] **Step 1: Create `frontend/src/components/SparqlPanel.tsx`**

```tsx
import { useState } from 'react'
import { t } from '../i18n/el'

type Props = {
  sparql: string
  streaming: boolean
}

export function SparqlPanel({ sparql, streaming }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  if (!sparql && !streaming) return null

  return (
    <div className="panel panel--emerald">
      <div className="panel-header">
        <div className="sparql-header-left">
          <span className="panel-label panel-label--emerald">{t.sparqlLabel}</span>
          {streaming
            ? <span className="status-pill status-pill--generating">{t.sparqlGenerating}</span>
            : <span className="status-pill status-pill--complete">{t.sparqlComplete}</span>
          }
        </div>
        <button
          className="collapse-btn"
          onClick={() => setCollapsed(c => !c)}
          aria-label={collapsed ? 'expand' : 'collapse'}
          type="button"
        >
          {collapsed ? t.sparqlExpand : t.sparqlCollapse}
        </button>
      </div>
      {!collapsed && (
        <pre className="sparql-code">
          {sparql}
          {streaming && <span className="cursor">▌</span>}
        </pre>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/components/SparqlPanel.tsx
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add SparqlPanel component with blinking cursor"
```

---

## Task 8: `ResultsTable` and `ErrorBanner` components

**Files:**
- Create: `frontend/src/components/ResultsTable.tsx`
- Create: `frontend/src/components/ErrorBanner.tsx`

- [ ] **Step 1: Create `frontend/src/components/ResultsTable.tsx`**

```tsx
import { t } from '../i18n/el'

type Props = {
  columns: string[]
  rows: Record<string, string>[]
  inputTokens: number
  outputTokens: number
  retries: number
}

export function ResultsTable({ columns, rows, inputTokens, outputTokens, retries }: Props) {
  return (
    <div className="panel panel--blue">
      <div className="panel-header">
        <span className="panel-label panel-label--blue">{t.resultsLabel}</span>
      </div>
      {rows.length === 0 ? (
        <p className="no-results">{t.noResults}</p>
      ) : (
        <div className="table-wrapper">
          <table className="results-table">
            <thead>
              <tr>
                {columns.map(col => <th key={col}>{col}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map(col => (
                    <td key={col}>{row[col] ?? ''}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="token-info">{t.tokenInfo(inputTokens, outputTokens, retries)}</p>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/components/ErrorBanner.tsx`**

```tsx
import { t } from '../i18n/el'

type Props = {
  message: string
  onDismiss: () => void
}

export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="panel panel--red error-banner" role="alert">
      <span><strong>{t.errorPrefix}</strong> {message}</span>
      <button
        className="dismiss-btn"
        onClick={onDismiss}
        aria-label={t.errorDismiss}
        type="button"
      >
        {t.errorDismiss}
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/components/ResultsTable.tsx frontend/src/components/ErrorBanner.tsx
git -C /c/Users/sotir/evdo-nlq commit -m "feat: add ResultsTable and ErrorBanner components"
```

---

## Task 9: `App.tsx` + `main.tsx` — wire everything

**Files:**
- Create: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Create `frontend/src/App.tsx`**

```tsx
import './styles.css'
import { useQueryStream } from './hooks/useQueryStream'
import { QueryForm } from './components/QueryForm'
import { SparqlPanel } from './components/SparqlPanel'
import { ResultsTable } from './components/ResultsTable'
import { ErrorBanner } from './components/ErrorBanner'
import { t } from './i18n/el'

export default function App() {
  const { state, providers, submit, dismissError } = useQueryStream()

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          {t.title} <span className="accent">{t.titleAccent}</span>
        </h1>
        <p>{t.subtitle}</p>
      </header>

      {state.status === 'error' && (
        <ErrorBanner message={state.message} onDismiss={dismissError} />
      )}

      <QueryForm
        providers={providers}
        disabled={state.status === 'streaming'}
        onSubmit={submit}
      />

      {(state.status === 'streaming' || state.status === 'done') && (
        <SparqlPanel
          sparql={state.sparql}
          streaming={state.status === 'streaming'}
        />
      )}

      {state.status === 'done' && (
        <ResultsTable
          columns={state.columns}
          rows={state.rows}
          inputTokens={state.inputTokens}
          outputTokens={state.outputTokens}
          retries={state.retries}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Replace `frontend/src/main.tsx`**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```

- [ ] **Step 3: Delete the scaffold files that are no longer needed**

```bash
rm /c/Users/sotir/evdo-nlq/frontend/src/index.css 2>/dev/null || true
rm /c/Users/sotir/evdo-nlq/frontend/src/App.css 2>/dev/null || true
rm -rf /c/Users/sotir/evdo-nlq/frontend/src/assets 2>/dev/null || true
```

- [ ] **Step 4: Typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/src/App.tsx frontend/src/main.tsx
git -C /c/Users/sotir/evdo-nlq commit -m "feat: wire App.tsx — complete frontend MVP"
```

---

## Task 10: Final smoke tests

No backend needed for the first two checks.

- [ ] **Step 1: Mock-API smoke test**

```bash
cd /c/Users/sotir/evdo-nlq/frontend
VITE_USE_MOCK_API=1 pnpm dev
```

Open `http://localhost:5173`. Verify:
- [ ] Page loads with dark background, gradient "NLQ" title
- [ ] Provider dropdown shows claude / gemini / fake; model dropdown updates when provider changes
- [ ] Type any question and click Αναζήτηση
- [ ] SPARQL panel appears with `● generating` pill and streaming characters
- [ ] After stream ends: `✓ complete` pill, collapse toggle works
- [ ] Results table appears below with 3 rows and token count footer
- [ ] Submitting again aborts the previous stream and starts fresh

Stop the server.

- [ ] **Step 2: Error-banner smoke test (mock)**

In `frontend/src/api/mock.ts`, temporarily add `throw new Error('test error')` before the first `yield`. Run `VITE_USE_MOCK_API=1 pnpm dev`, submit a query, confirm the red `ErrorBanner` appears. Click ✕ — it should dismiss. Revert the temporary change.

- [ ] **Step 3: Real backend + fake LLM (no tokens)**

```bash
# Terminal 1
cd /c/Users/sotir/evdo-nlq/backend
LLM_PROVIDER=fake uv run fastapi dev app/main.py

# Terminal 2
cd /c/Users/sotir/evdo-nlq/frontend
pnpm dev
```

Open `http://localhost:5173`. Verify:
- [ ] Provider dropdown is populated from `GET /providers` (claude, gemini, fake)
- [ ] Select `fake / fake-v1`, submit "Πόσα βιβλία;"
- [ ] SPARQL streams, results table shows real GraphDB data

- [ ] **Step 4: Final typecheck**

```bash
cd /c/Users/sotir/evdo-nlq/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 5: Final commit**

```bash
git -C /c/Users/sotir/evdo-nlq add frontend/
git -C /c/Users/sotir/evdo-nlq commit -m "chore: remove default scaffold files"
```

---

## Deliverables checklist

- [ ] `pnpm dev` runs at `:5173`
- [ ] `pnpm typecheck` passes
- [ ] Mock mode: all 4 components render correctly
- [ ] Provider dropdown populated from `GET /providers`
- [ ] Live SPARQL streaming visible (typewriter effect)
- [ ] Results table renders with correct columns/rows
- [ ] Error banner shows and dismisses
- [ ] All visible strings in Greek (from `i18n/el.ts`)
- [ ] Visual style: dark + emerald SPARQL + blue results
