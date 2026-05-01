import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { streamQuery } from '../api/client'
import type { Provider, QueryState } from '../types'

/**
 * Discriminated-union action type for the query state machine.
 *
 * Flow: idle → (SUBMIT) → streaming → (DONE) → done
 *                                   → (ERROR) → error → (DISMISS_ERROR) → idle
 *
 * RESULTS arrives while still in `streaming` and caches `columns`/`rows` so
 * they are ready when DONE fires.
 */
type Action =
  | { type: 'SUBMIT' }
  | { type: 'TOKEN'; payload: string }
  | { type: 'COMPLETE'; payload: string }
  | { type: 'RESULTS'; payload: { columns: string[]; rows: Record<string, string | undefined>[] } }
  | { type: 'DONE'; payload: { inputTokens: number; outputTokens: number; retries: number } }
  | { type: 'ERROR'; payload: string }
  | { type: 'DISMISS_ERROR' }

/**
 * Pure reducer — all state transitions live here so they are easy to test in
 * isolation.  Guards on `state.status` prevent stale events from corrupting
 * state after an abort or error.
 */
function reducer(state: QueryState, action: Action): QueryState {
  switch (action.type) {
    case 'SUBMIT':
      // Reset to a clean streaming state; discard any previous results.
      return { status: 'streaming', sparql: '' }

    case 'TOKEN':
      // Append a single SPARQL token streamed from the backend.
      if (state.status !== 'streaming') return state
      return { ...state, sparql: state.sparql + action.payload }

    case 'COMPLETE':
      // Replace sparql with the final, authoritative SPARQL string.
      if (state.status !== 'streaming') return state
      return { ...state, sparql: action.payload }

    case 'RESULTS':
      // Store query results while still streaming — they arrive before `done`.
      if (state.status !== 'streaming') return state
      return { ...state, columns: action.payload.columns, rows: action.payload.rows }

    case 'DONE':
      // Transition to the terminal `done` state; pull columns/rows from streaming state.
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

/**
 * Core state-management hook for the NL-to-SPARQL pipeline.
 *
 * Returns:
 * - `state`        — current `QueryState` (idle | streaming | done | error)
 * - `providers`    — list of available LLM providers fetched from GET /providers
 * - `submit`       — fire off a new query; aborts any in-flight request first
 * - `dismissError` — transition from `error` back to `idle`
 *
 * Abort behaviour:
 * - Every `submit()` call aborts the previous `AbortController` before creating
 *   a new one, so only one SSE stream is alive at a time.
 * - On unmount the `useEffect` cleanup also aborts to prevent state updates on
 *   an unmounted component.
 * - `AbortError` exceptions are swallowed — they indicate intentional
 *   cancellation, not a failure the user needs to see.
 */
export function useQueryStream() {
  const [state, dispatch] = useReducer(reducer, { status: 'idle' })
  const [providers, setProviders] = useState<Provider[]>([])
  const abortRef = useRef<AbortController | null>(null)

  // Fetch available providers once on mount.
  useEffect(() => {
    let cancelled = false

    if (import.meta.env.VITE_USE_MOCK_API === '1') {
      // Hard-coded providers for UI development — no network call needed.
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
      // Cancel the fetch guard and abort any live SSE stream.
      cancelled = true
      abortRef.current?.abort()
    }
  }, [])

  /**
   * Submit a natural-language question to the backend SSE pipeline.
   *
   * Aborts any in-flight request before starting a new one.  The IIFE lets us
   * use `async/await` inside `useCallback` without making the callback itself
   * async (which would return a Promise and confuse React event handlers).
   */
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
              const parsed = JSON.parse(data) as { columns: string[]; rows: Record<string, string | undefined>[] }
              dispatch({ type: 'RESULTS', payload: parsed })
              break
            }

            case 'done': {
              const parsed = JSON.parse(data) as { input_tokens: number; output_tokens: number; retries: number }
              dispatch({
                type: 'DONE',
                payload: {
                  inputTokens: parsed.input_tokens,
                  outputTokens: parsed.output_tokens,
                  retries: parsed.retries,
                },
              })
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
        // Only surface genuine errors — AbortError means the user cancelled.
        if (err instanceof Error && err.name !== 'AbortError') {
          dispatch({ type: 'ERROR', payload: err.message })
        }
      }
    })()
  }, [])

  /** Transition from the `error` state back to `idle` so the user can retry. */
  const dismissError = useCallback(() => dispatch({ type: 'DISMISS_ERROR' }), [])

  return { state, providers, submit, dismissError }
}
