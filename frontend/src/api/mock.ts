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

/** Returns a promise that resolves after `ms` milliseconds, or rejects if the AbortSignal fires first. */
function delay(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
  })
}

/**
 * Mock SSE stream that simulates the backend pipeline without any network calls.
 *
 * Emits one SPARQL character every 18 ms (typewriter effect), then a results event,
 * then a done event. Respects the AbortSignal so the UI cancel button works in mock mode.
 *
 * Activated when VITE_USE_MOCK_API=1.
 */
export async function* mockStreamQuery(
  _question: string,
  provider: string,
  model: string,
  signal: AbortSignal,
): AsyncGenerator<ParsedSSEEvent> {
  // Stream the SPARQL query one character at a time to simulate the typewriter effect.
  for (const char of MOCK_SPARQL) {
    await delay(18, signal)
    yield { event: 'sparql_token', data: char }
  }

  // Note: sparql_retry events are not modelled here — retry UI can only be
  // tested with the real backend (LLM_PROVIDER=claude/gemini + invalid prompt).

  // Signal that the full SPARQL string is available.
  yield { event: 'sparql_complete', data: MOCK_SPARQL }

  // Simulate a brief pause while "executing" the SPARQL query.
  await delay(300, signal)
  yield { event: 'results', data: JSON.stringify(MOCK_RESULTS) }

  // Final bookkeeping event with token-usage metadata.
  await delay(50, signal)
  yield {
    event: 'done',
    data: JSON.stringify({ provider, model, input_tokens: 120, output_tokens: 45, retries: 0 }),
  }
}
