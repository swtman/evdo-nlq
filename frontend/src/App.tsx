/**
 * App — the root component that wires everything together.
 *
 * Owns the history overlay open/close state and the "dual display path":
 * results are shown from either the live query state OR a cached history entry,
 * whichever is active. All other state lives in the hooks it calls.
 *
 * Layout:
 *   sidebar overlay (history) + main column (header, form, SPARQL panel, results/error)
 */

import { useState, useEffect } from 'react'
import './styles.css'
import { useQueryStream } from './hooks/useQueryStream'
import { useHistory } from './hooks/useHistory'
import { QueryForm } from './components/QueryForm'
import { SparqlPanel } from './components/SparqlPanel'
import { ResultsTable } from './components/ResultsTable/ResultsTable'
import { ErrorBanner } from './components/ErrorBanner'
import { HistorySidebar } from './components/HistorySidebar'
import { t } from './i18n/el'
import type { HistoryEntry } from './types'

type Theme = 'dark' | 'light'

function getInitialTheme(): Theme {
  // Read from localStorage so the preference survives page reloads.
  return (localStorage.getItem('theme') as Theme | null) ?? 'light'
}

// Short git SHA injected by Vite at build time via VITE_GIT_SHA env var.
// Falls back to 'dev' in development when the var isn't set.
const GIT_SHA = (import.meta.env.VITE_GIT_SHA as string | undefined)?.slice(0, 7) ?? 'dev'

export default function App() {
  const { state, providers, submit, dismissError, clear } = useQueryStream()
  const { entries, addEntry, clearHistory } = useHistory()

  const [submissionCount, setSubmissionCount] = useState(0)
  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [cachedResult, setCachedResult] = useState<HistoryEntry | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  // Captures the question/provider/model of the in-flight query so we can write
  // to history when the `done` or `error` event arrives.
  const [pendingMeta, setPendingMeta] = useState<{
    question: string; provider: string; model: string
  } | null>(null)

  // Tracks the provider/model used in the last submission so that example-query
  // clicks in EmptyState reuse the same model (without the user having to reselect).
  const [lastMeta, setLastMeta] = useState<{ provider: string; model: string } | null>(null)

  // Drives QueryForm's `prefillQuestion` prop — set when an example or history item
  // is clicked so the input reflects what's currently being displayed.
  const [prefillQuestion, setPrefillQuestion] = useState<string | undefined>(undefined)

  // Apply theme to the <html> element and persist the choice.
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))

  // Write to history when a query finishes (done) or fails (error).
  // We watch state.status rather than state itself to fire only on transitions.
  useEffect(() => {
    if (!pendingMeta) return
    if (state.status === 'done') {
      addEntry({
        question: pendingMeta.question,
        provider: pendingMeta.provider,
        model: pendingMeta.model,
        sparql: state.sparql,
        columns: state.columns,
        rows: state.rows,
        retries: state.retries,
        inputTokens: state.inputTokens,
        outputTokens: state.outputTokens,
      })
      setPendingMeta(null)
    } else if (state.status === 'error') {
      addEntry({
        question: pendingMeta.question,
        provider: pendingMeta.provider,
        model: pendingMeta.model,
        sparql: state.sparql,
        columns: [],
        rows: [],
        error: state.message,
        retries: 0,
        inputTokens: 0,
        outputTokens: 0,
      })
      setPendingMeta(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status])

  /** Reset to idle and clear all derived display state. */
  const handleClear = () => {
    clear()
    setActiveHistoryId(null)
    setCachedResult(null)
    setPrefillQuestion('')
    setPendingMeta(null)
    // Incrementing submissionCount remounts <SparqlPanel>, resetting its collapsed state.
    setSubmissionCount(c => c + 1)
  }

  /** Fire a new query and track metadata for the eventual history write. */
  const handleSubmit = (question: string, provider: string, model: string) => {
    setSubmissionCount(c => c + 1) // forces SparqlPanel remount (see key={submissionCount})
    setActiveHistoryId(null)
    setCachedResult(null)
    setPendingMeta({ question, provider, model })
    setLastMeta({ provider, model })
    submit(question, provider, model)
  }

  /** Load a cached result from history without hitting the backend. */
  const handleHistorySelect = (entry: HistoryEntry) => {
    setActiveHistoryId(entry.id)
    setCachedResult(entry)
    // Sync the input so it reflects the cached query (not the previous live query).
    setPrefillQuestion(entry.question)
    setHistoryOpen(false)
  }

  // ── Dual display path ──────────────────────────────────────────────────────
  // `cachedResult` takes precedence over live state via the ?? operator.
  // When a history entry is selected, the cached SPARQL/rows are displayed even
  // though state.status may still be 'idle' or 'done' from the previous query.

  const sparqlToShow =
    cachedResult?.sparql ??
    (state.status === 'streaming' || state.status === 'done'
      ? state.sparql
      : state.status === 'error'
      ? state.sparql // may be undefined if the error fired before any SPARQL arrived
      : undefined)

  const showSparqlPanel = Boolean(sparqlToShow || state.status === 'streaming')

  const liveResult = state.status === 'done' ? state : null
  const displayColumns = cachedResult?.columns ?? liveResult?.columns
  const displayRows    = cachedResult?.rows    ?? liveResult?.rows
  const displayTokenInfo = cachedResult
    ? { inputTokens: cachedResult.inputTokens, outputTokens: cachedResult.outputTokens, retries: cachedResult.retries }
    : liveResult
    ? { inputTokens: liveResult.inputTokens,   outputTokens: liveResult.outputTokens,   retries: liveResult.retries }
    : null

  return (
    <div className="app-frame">

      {/* ── History overlay: clicking the backdrop closes it ── */}
      <div
        className={`sidebar-overlay${historyOpen ? ' open' : ''}`}
        onClick={() => setHistoryOpen(false)}
      >
        {/* stopPropagation prevents the panel click from bubbling to the backdrop. */}
        <div className="sidebar-overlay-panel" onClick={e => e.stopPropagation()}>
          <HistorySidebar
            entries={entries}
            activeId={activeHistoryId}
            onSelect={handleHistorySelect}
            onClear={clearHistory}
          />
        </div>
      </div>

      {/* ── Main content column ── */}
      <main className="app-main">

        {/* ── Header ── */}
        <header className="app-header">
          <div className="header-left">
            <div className="header-title">
              {t.title}{' '}
              <span className="accent">{t.titleAccent}</span>
              {/* Green pulsing square — purely decorative, so aria-hidden. */}
              <span className="live-dot" aria-hidden="true" />
            </div>
            <p className="header-subtitle">{t.subtitle}</p>
          </div>
          <div className="header-meta">
            <span><span className="version">v0.1.0</span> · build {GIT_SHA}</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className="history-toggle"
                onClick={() => setHistoryOpen(p => !p)}
                aria-label="Ιστορικό ερωτημάτων"
              >
                {t.historyMobileToggle(entries.length)}
              </button>
              <button
                className="theme-toggle"
                onClick={toggleTheme}
                aria-label={theme === 'dark' ? t.switchToLight : t.switchToDark}
              >
                {theme === 'dark' ? '☀ light' : '☾ dark'}
              </button>
            </div>
          </div>
        </header>

        {/* ── Search form ── */}
        <QueryForm
          providers={providers}
          disabled={state.status === 'streaming'}
          onSubmit={handleSubmit}
          prefillQuestion={prefillQuestion}
          showClear={state.status !== 'idle' || cachedResult !== null}
          onClear={handleClear}
        />

        {/* ── SPARQL panel ──
            key={submissionCount} force-remounts the panel on each new query so its
            internal `collapsed` state resets cleanly without any prop-drilling. */}
        {showSparqlPanel && (
          <SparqlPanel
            key={submissionCount}
            sparql={sparqlToShow ?? ''}
            streaming={state.status === 'streaming'}
            executing={state.status === 'streaming' && !!state.executing}
          />
        )}

        {/* ── Results table (live or cached) ── */}
        {displayColumns && displayRows && displayTokenInfo && (
          <ResultsTable
            columns={displayColumns}
            rows={displayRows}
            inputTokens={displayTokenInfo.inputTokens}
            outputTokens={displayTokenInfo.outputTokens}
            retries={displayTokenInfo.retries}
            isCached={!!cachedResult}
            onExampleSelect={(question: string) => {
              // Reuse the last-used model; fall back to the first available.
              const provider = lastMeta?.provider ?? providers[0]?.id ?? ''
              const model    = lastMeta?.model    ?? providers[0]?.models[0] ?? ''
              setPrefillQuestion(question)
              handleSubmit(question, provider, model)
            }}
          />
        )}

        {/* ── Error banner ──
            Suppressed when showing a cached history entry so the old error
            from the live query doesn't bleed through. */}
        {!cachedResult && state.status === 'error' && (
          <ErrorBanner message={state.message} onDismiss={dismissError} />
        )}

      </main>
    </div>
  )
}
