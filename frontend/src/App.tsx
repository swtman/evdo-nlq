import { useState } from 'react'
import './styles.css'
import { useQueryStream } from './hooks/useQueryStream'
import { QueryForm } from './components/QueryForm'
import { SparqlPanel } from './components/SparqlPanel'
import { ResultsTable } from './components/ResultsTable'
import { ErrorBanner } from './components/ErrorBanner'
import { t } from './i18n/el'

/**
 * App — top-level component that wires the NL-to-SPARQL pipeline together.
 *
 * Layout:
 *   header → error banner (conditional) → query form → SPARQL panel → results table
 *
 * State is owned by `useQueryStream`; App only handles the `submissionCount`
 * counter that re-mounts `SparqlPanel` on each new query so its internal
 * `collapsed` state resets cleanly.
 */
export default function App() {
  const { state, providers, submit, dismissError } = useQueryStream()

  /**
   * Incremented on every submit to force React to re-mount `SparqlPanel`.
   * This resets the panel's internal `collapsed` state for each new query
   * without having to lift that state up into App.
   */
  const [submissionCount, setSubmissionCount] = useState(0)

  /** Wrap `submit` so we can bump the counter before firing the query. */
  const handleSubmit = (question: string, provider: string, model: string) => {
    setSubmissionCount(c => c + 1)
    submit(question, provider, model)
  }

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
        onSubmit={handleSubmit}
      />

      {(state.status === 'streaming' || state.status === 'done') && (
        <SparqlPanel
          key={submissionCount}
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
