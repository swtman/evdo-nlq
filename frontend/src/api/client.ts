import type { ParsedSSEEvent } from '../types'

/**
 * Streams a natural-language query through the backend pipeline.
 *
 * Yields `ParsedSSEEvent` objects as they arrive from the SSE stream.
 * Possible event names: `sparql_token`, `sparql_complete`, `results`, `done`, `error`.
 *
 * When the `VITE_USE_MOCK_API` env var is `"1"`, the function delegates to the
 * local mock module so no network calls are made — useful for UI development
 * without spending LLM tokens.
 *
 * @param question  Natural-language question from the user.
 * @param provider  LLM provider id (e.g. "claude", "fake").
 * @param model     Model id within the provider (e.g. "claude-haiku-4-5").
 * @param signal    AbortSignal — pass `controller.signal` so the caller can cancel.
 */
export async function* streamQuery(
  question: string,
  provider: string,
  model: string,
  signal: AbortSignal,
): AsyncGenerator<ParsedSSEEvent> {
  // In mock mode, delegate entirely to the local fake implementation.
  if (import.meta.env.VITE_USE_MOCK_API === '1') {
    const { mockStreamQuery } = await import('./mock')
    yield* mockStreamQuery(question, provider, model, signal)
    return
  }

  // POST the question to the backend SSE endpoint.
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

  // SSE messages are separated by double newlines (\n\n).
  // We accumulate incomplete chunks in `buffer` until a full message arrives.
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Split on the SSE message delimiter.
      const parts = buffer.split('\n\n')

      // The last element is either empty or an incomplete message — keep it in the buffer.
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        if (!part.trim()) continue

        // Parse the `event:` and `data:` fields from each SSE message block.
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
    // Always release the reader lock, even if we were aborted.
    reader.releaseLock()
  }
}
