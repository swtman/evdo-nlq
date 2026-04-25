# frontend/ — React + Vite UI

Minimal single-page app: input box for NL question, submit button, results table, and a collapsible panel showing the generated SPARQL.

## Stack

- React 18 + TypeScript
- Vite (dev server on :5173, build with `pnpm build`)
- Plain CSS (no Tailwind for now — see ADR-005 if/when we change)
- `fetch` for API calls (no React Query yet; add if needed)

## Scaffold command (once, when creating this folder for real)

```bash
cd frontend
pnpm create vite . --template react-ts
pnpm install
pnpm add -D @types/node
```

## Commands

```bash
pnpm dev          # dev server (hot reload) on http://localhost:5173
pnpm build        # production build
pnpm preview      # serve production build locally
pnpm typecheck    # tsc --noEmit
pnpm lint         # eslint (if configured)
```

## Layout (intended)

```
src/
├── main.tsx            entrypoint
├── App.tsx             single top-level component
├── components/
│   ├── QueryForm.tsx   input + submit
│   ├── ResultsTable.tsx
│   ├── SparqlPanel.tsx generated SPARQL, collapsible
│   └── ErrorBanner.tsx
├── api/
│   └── client.ts       fetch wrapper for POST /query
├── types.ts            shared TS types that mirror backend Pydantic schemas
└── styles.css
```

## Working without burning tokens

The frontend should be built and iterated on **without any live LLM calls**:

- When `VITE_USE_MOCK_API=1`, `src/api/client.ts` returns hand-crafted fake responses instead of hitting the backend. Use this for layout/CSS work.
- When hitting the real backend in development, the backend should have `LLM_PROVIDER=fake` (see `backend/.env.example`). Same effect, no tokens spent.
- Only flip to the real provider when you're deliberately testing the full pipeline.

## API contract (v1)

```
POST /query
Request:  { "question": "string", "provider"?: "claude"|"openai"|"ollama" }
Response: {
  "question": "string",
  "sparql": "string",
  "results": { "columns": string[], "rows": Record<string, string>[] },
  "provider": "string",
  "model": "string",
  "latency_ms": number,
  "token_usage": { "input": number, "output": number } | null
}
Error:    { "error_type": "llm_error"|"sparql_error"|"endpoint_error", "message": "string", "details"?: any }
```

The backend is the source of truth for this schema — if it changes, regenerate `src/types.ts`.

## Language

- UI copy: **Greek** (primary). Keep strings in `src/i18n/el.ts` so an English pass is a one-line swap.
- Code, comments, component names, commit messages: **English**.

## What NOT to do

- Don't call the LLM from the frontend. Only the backend talks to LLMs.
- Don't parse or transform SPARQL on the frontend. Display-only.
- Don't hardcode the GraphDB endpoint — everything goes through the backend.
