/**
 * Shared TypeScript types used across the entire frontend.
 * Read this file first — every hook and component is shaped by these types.
 */

/** One LLM provider (e.g. "claude") and its available models. Populated from GET /providers. */
export type Provider = {
  id: string       // e.g. "claude", "gemini", "fake"
  models: string[] // e.g. ["claude-haiku-4-5", "claude-sonnet-4-6"]
}

/** One parsed event from the backend SSE stream. Produced by api/client.ts and api/mock.ts. */
export type ParsedSSEEvent = {
  event: string // e.g. "sparql_token", "results", "done", "error"
  data: string  // JSON string or raw token text depending on the event type
}

/**
 * The entire UI state lives in this discriminated union.
 * Switch on `status` to know exactly which fields are available.
 *
 *   idle → (user submits) → streaming → (done event) → done
 *                                     → (error event) → error → (dismiss) → idle
 */
export type QueryState =
  | { status: 'idle' }
  | {
      status: 'streaming'
      sparql: string           // SPARQL text accumulated so far (grows token by token)
      executing?: boolean      // true between sparql_complete and results — GraphDB is running
      columns?: string[]       // arrive with the results event, before DONE is dispatched
      rows?: Record<string, string | undefined>[]
    }
  | {
      status: 'done'
      sparql: string
      columns: string[]
      rows: Record<string, string | undefined>[]
      inputTokens: number   // LLM tokens consumed in the prompt
      outputTokens: number  // LLM tokens produced (the SPARQL)
      retries: number       // how many times the backend retried invalid SPARQL
    }
  | {
      status: 'error'
      message: string
      sparql?: string // preserved if SPARQL was generated before the error, so the panel stays visible
    }

/**
 * One entry saved to localStorage history when a query completes (or errors).
 * Contains everything needed to redisplay the result without hitting the backend again.
 */
export type HistoryEntry = {
  id: string        // crypto.randomUUID() — stable key for React lists
  timestamp: number // Date.now() — used to display HH:mm in the sidebar
  question: string  // the original natural-language question
  provider: string
  model: string
  sparql?: string   // undefined when the query errored before any SPARQL was produced
  columns: string[]
  rows: Record<string, string | undefined>[]
  error?: string    // set when the query ended in an error state
  retries: number
  inputTokens: number
  outputTokens: number
}

/** Which direction a column is sorted. Cycling order: idle → asc → desc → idle. */
export type SortDirection = 'idle' | 'asc' | 'desc'

/** Active sort column and direction. `column: null` means no sort is active. */
export type SortState = {
  column: string | null
  direction: SortDirection
}

/**
 * Tracks which columns are visible in the results table.
 * A missing key means "visible" — only hidden columns have an entry (`false`).
 * Resets to `{}` (all visible) on every new query.
 */
export type ColumnVisibility = Record<string, boolean>
