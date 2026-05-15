/**
 * Mock backend for UI development.
 *
 * Activated by setting VITE_USE_MOCK_API=1 before running `pnpm dev`.
 * The mock is dynamically imported in api/client.ts so it is never included
 * in production builds — only the development bundle loads this file.
 *
 * Use this when you want to work on layout, animations, or component logic
 * without a running backend or API keys.
 *
 * Limitation: sparql_retry events are NOT simulated. To test retry UI, use
 * the real backend with LLM_PROVIDER=fake and a prompt that produces bad SPARQL.
 */

import type { ParsedSSEEvent } from '../types'

// A realistic SPARQL query used as the mock "generated" output.
const MOCK_SPARQL = `PREFIX evdx: <https://w3id.org/evdoxus#>
select distinct ?University ?Name where{
    ?University a evdx:University.
	?University evdx:name ?Name.
}
Groupby ?University ?Name `

export const MOCK_RESULTS = {
  columns: ['University', 'Name'],
  rows: [
    {
      University: 'https://w3id.org/evdoxus#university_1',
      Name: 'ΑΛΕΞΑΝΔΡΕΙΟ ΤΕΙ ΘΕΣΣΑΛΟΝΙΚΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_10',
      Name: 'ΓΕΩΠΟΝΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_11',
      Name: 'ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_12',
      Name: 'ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_13',
      Name: 'ΕΘΝΙΚΟ ΜΕΤΣΟΒΙΟ ΠΟΛΥΤΕΧΝΕΙΟ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_14',
      Name: 'ΙΟΝΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_15',
      Name: 'ΟΙΚΟΝΟΜΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_16',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΙΓΑΙΟΥ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_17',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΕΛΛΑΔΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_18',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΜΑΚΕΔΟΝΙΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_19',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_2',
      Name: 'ΑΝΩΤΑΤΗ ΕΚΚΛΗΣΙΑΣΤΙΚΗ ΑΚΑΔΗΜΙΑ ΑΘΗΝΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_20',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΙΩΑΝΝΙΝΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_21',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΚΡΗΤΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_22',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΜΑΚΕΔΟΝΙΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_23',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΑΤΡΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_24',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_25',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΛΟΠΟΝΝΗΣΟΥ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_26',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΣΤΕΡΕΑΣ ΕΛΛΑΔΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_27',
      Name: 'ΠΑΝΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΚΟΙΝΩΝΙΚΩΝ & ΠΟΛΙΤΙΚΩΝ ΕΠΙΣΤΗΜΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_28',
      Name: 'ΠΟΛΥΤΕΧΝΕΙΟ ΚΡΗΤΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_29',
      Name: 'ΤΕΙ ΑΘΗΝΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_3',
      Name: 'ΑΝΩΤΑΤΗ ΕΚΚΛΗΣΙΑΣΤΙΚΗ ΑΚΑΔΗΜΙΑ ΒΕΛΛΑΣ ΙΩΑΝΝΙΝΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_30',
      Name: 'ΤΕΙ ΔΥΤΙΚΗΣ ΜΑΚΕΔΟΝΙΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_31',
      Name: 'ΤΕΙ ΗΠΕΙΡΟΥ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_32',
      Name: 'ΤΕΙ ΙΟΝΙΩΝ ΝΗΣΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_33',
      Name: 'ΤΕΙ ΑΝΑΤΟΛΙΚΗΣ ΜΑΚΕΔΟΝΙΑΣ ΚΑΙ ΘΡΑΚΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_34',
      Name: 'ΤΕΙ ΠΕΛΟΠΟΝΝΗΣΟΥ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_35',
      Name: 'ΤΕΙ ΚΡΗΤΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_36',
      Name: 'ΤΕΙ ΣΤΕΡΕΑΣ ΕΛΛΑΔΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_37',
      Name: 'ΤΕΙ ΘΕΣΣΑΛΙΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_38',
      Name: 'ΤΕΙ ΜΕΣΟΛΟΓΓΙΟΥ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_39',
      Name: 'ΤΕΙ ΔΥΤΙΚΗΣ ΕΛΛΑΔΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_4',
      Name: 'ΠΑΤΡΙΑΡΧΙΚΗ ΑΝΩΤΑΤΗ ΕΚΚΛΗΣΙΑΣΤΙΚΗ ΑΚΑΔΗΜΙΑ ΚΡΗΤΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_40',
      Name: 'ΤΕΙ ΠΕΙΡΑΙΑ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_41',
      Name: 'ΤΕΙ ΚΕΝΤΡΙΚΗΣ ΜΑΚΕΔΟΝΙΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_42',
      Name: 'ΤΕΙ ΧΑΛΚΙΔΑΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_43',
      Name: 'ΧΑΡΟΚΟΠΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_44',
      Name: 'ΕΛΛΗΝΙΚΟ ΑΝΟΙΧΤΟ ΠΑΝΕΠΙΣΤΗΜΙΟ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_45',
      Name: 'ΔΙΕΘΝΕΣ ΠΑΝΕΠΙΣΤΗΜΙΟ ΤΗΣ ΕΛΛΑΔΟΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_47',
      Name: 'ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_48',
      Name: 'ΕΛΛΗΝΙΚΟ ΜΕΣΟΓΕΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_5',
      Name: 'ΑΝΩΤΑΤΗ ΕΚΚΛΗΣΙΑΣΤΙΚΗ ΑΚΑΔΗΜΙΑ ΘΕΣΣΑΛΟΝΙΚΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_6',
      Name: 'ΑΝΩΤΑΤΗ ΣΧΟΛΗ ΚΑΛΩΝ ΤΕΧΝΩΝ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_8',
      Name: 'ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ'
    },
    {
      University: 'https://w3id.org/evdoxus#university_9',
      Name: 'ΑΣΠΑΙΤΕ'
    }
  ]
} as const;

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
