import { useState, useEffect } from 'react'
import './styles.css'
import { useQueryStream } from './hooks/useQueryStream'
import { QueryForm } from './components/QueryForm'
import { SparqlPanel } from './components/SparqlPanel'
import { ResultsTable } from './components/ResultsTable'
import { ErrorBanner } from './components/ErrorBanner'
import { t } from './i18n/el'

type Theme = 'dark' | 'light'

function getInitialTheme(): Theme {
  return (localStorage.getItem('theme') as Theme | null) ?? 'dark'
}

/**
 * App — top-level component that wires the NL-to-SPARQL pipeline together.
 *
 * Layout:
 *   header (+ theme toggle) → query form → SPARQL panel →
 *   graphdb indicator (while executing) → results table OR error banner
 *
 * State is owned by `useQueryStream`; App handles the `submissionCount`
 * counter that re-mounts `SparqlPanel` on each new query so its internal
 * `collapsed` state resets cleanly.
 */
export default function App() {
  const { state, providers, submit, dismissError } = useQueryStream()

  const [submissionCount, setSubmissionCount] = useState(0)
  const [theme, setTheme] = useState<Theme>(getInitialTheme)

  // Apply theme attribute to <html> and persist to localStorage.
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))

  /** Wrap `submit` so we can bump the counter before firing the query. */
  const handleSubmit = (question: string, provider: string, model: string) => {
    setSubmissionCount(c => c + 1)
    submit(question, provider, model)
  }

  // Derive the SPARQL to display. On error, show whatever was generated before
  // the failure so the user can see which query caused the problem.
  const sparqlToShow =
    state.status === 'streaming' || state.status === 'done'
      ? state.sparql
      : state.status === 'error'
      ? state.sparql          // may be undefined if error occurred before any SPARQL
      : undefined

  const showSparqlPanel = Boolean(
    sparqlToShow || state.status === 'streaming'
  )

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          {t.title} <span className="accent">{t.titleAccent}</span>
        </h1>
        <p>{t.subtitle}</p>
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? t.switchToLight : t.switchToDark}
          title={theme === 'dark' ? t.switchToLight : t.switchToDark}
        >
          {theme === 'dark' ? '☀' : '🌙'}
        </button>
      </header>

      <QueryForm
        providers={providers}
        disabled={state.status === 'streaming'}
        onSubmit={handleSubmit}
      />

      {showSparqlPanel && (
        <SparqlPanel
          key={submissionCount}
          sparql={sparqlToShow ?? ''}
          streaming={state.status === 'streaming'}
        />
      )}

      {/* Shown between sparql_complete and results — GraphDB is running the query */}
      {state.status === 'streaming' && state.executing && (
        <div className="graphdb-indicator" role="status" aria-live="polite">
          <span className="graphdb-dot" aria-hidden="true" />
          <span>{t.graphdbExecuting}</span>
        </div>
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

      {/* Error appears in the results area, below the SPARQL panel */}
      {state.status === 'error' && (
        <ErrorBanner message={state.message} onDismiss={dismissError} />
      )}
    </div>
  )
}
