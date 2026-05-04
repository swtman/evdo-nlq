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
 * Throws DOMException('AbortError') when signal fires — callers should check
 * `error.name === 'AbortError'` to distinguish user cancellation from failures.
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

  // SSE messages are separated by double newlines.
  // We accumulate incomplete chunks in `buffer` until a full message arrives.
  // sse_starlette (the backend SSE library) uses \r\n line endings and \r\n\r\n
  // event separators. We normalize CRLF → LF after every read so the rest of
  // the parser only needs to handle \n.
  let buffer = ''

  /**
   * Parse and yield all SSE event blocks present in `text`.
   * Expects LF-only line endings (call after CRLF normalisation).
   * Handles multi-line data fields by concatenating them with \n.
   */
  function* parseBlocks(text: string): Generator<ParsedSSEEvent> {
    for (const part of text.split('\n\n')) {
      if (!part.trim()) continue
      let event = ''
      const dataLines: string[] = []
      for (const line of part.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
      }
      const data = dataLines.join('\n').trim()
      if (event && data) yield { event, data }
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()

      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      // Normalise CRLF to LF so \n\n reliably marks event boundaries.
      buffer = buffer.replace(/\r\n/g, '\n')

      const parts = buffer.split('\n\n')
      // On stream end: keep all parts so the final event (which may lack a
      // trailing \n\n) is also processed. On a normal read: keep the last
      // element as an incomplete fragment for the next iteration.
      buffer = done ? '' : (parts.pop() ?? '')

      yield* parseBlocks(parts.join('\n\n'))

      if (done) break
    }
  } finally {
    // Always release the reader lock, even if we were aborted.
    reader.releaseLock()
  }
}
