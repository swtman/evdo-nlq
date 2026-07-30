/**
 * App — root component; wires shell layout (rail + header + hero + content) and
 * all global state (theme, history overlay, dual display path, query lifecycle).
 *
 * Layout (Console theme, ADR-016):
 *   .app-rail  (64 px sticky left rail — logo + theme toggle)
 *   .app-main  (flex column)
 *     .app-header  (topbar: brand + tabs + status)
 *     .hero        (eyebrow + h1 + QueryForm + example chips)
 *     .content-wrap
 *       question-echo (when query is active)
 *       SparqlPanel
 *       ResultsTable
 *       ErrorBanner
 *
 * History overlay: full-screen backdrop + left-sliding drawer (HistorySidebar).
 * Dual display path: cachedResult ?? live state (same as before).
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
import { OntologyPage } from './components/OntologyPage'
import { t } from './i18n/el'
import type { HistoryEntry } from './types'

type Theme = 'dark' | 'light'
type View = 'query' | 'ontology'

/** Read stored preference, then OS default, then 'light'. */
function getInitialTheme(): Theme {
  const stored = localStorage.getItem('theme') as Theme | null
  if (stored === 'dark' || stored === 'light') return stored
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

const GIT_SHA = (import.meta.env.VITE_GIT_SHA as string | undefined)?.slice(0, 7) ?? 'dev'

export default function App() {
  const { state, providers, submit, rerunSparql, dismissError, clear } = useQueryStream()
  const { entries, addEntry, clearHistory } = useHistory()

  const [submissionCount, setSubmissionCount] = useState(0)
  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const [view, setView] = useState<View>('query')
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [cachedResult, setCachedResult] = useState<HistoryEntry | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const [pendingMeta, setPendingMeta] = useState<{
    question: string; provider: string; model: string
  } | null>(null)
  const [lastMeta, setLastMeta] = useState<{ provider: string; model: string } | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [prefillQuestion, setPrefillQuestion] = useState<string | undefined>(undefined)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))

  // Write to history when a query finishes (done) or fails (error).
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

  const handleClear = () => {
    clear()
    setActiveHistoryId(null)
    setCachedResult(null)
    setPrefillQuestion('')
    setPendingMeta(null)
    setCurrentQuestion('')
    setSubmissionCount(c => c + 1)
  }

  const handleSubmit = (question: string, provider: string, model: string) => {
    setSubmissionCount(c => c + 1)
    setActiveHistoryId(null)
    setCachedResult(null)
    setPendingMeta({ question, provider, model })
    setLastMeta({ provider, model })
    setCurrentQuestion(question)
    submit(question, provider, model)
  }

  const handleRerun = (editedSparql: string) => {
    setSubmissionCount(c => c + 1)
    setActiveHistoryId(null)
    setCachedResult(null)
    const baseQuestion = currentQuestion.startsWith(t.historyManualEdit)
      ? currentQuestion.slice(t.historyManualEdit.length).trimStart()
      : currentQuestion
    setPendingMeta({
      question: `${t.historyManualEdit} ${baseQuestion}`.trim(),
      provider: lastMeta?.provider ?? '—',
      model:    lastMeta?.model    ?? '—',
    })
    setCurrentQuestion(`${t.historyManualEdit} ${baseQuestion}`.trim())
    rerunSparql(editedSparql)
  }

  const handleHistorySelect = (entry: HistoryEntry) => {
    setActiveHistoryId(entry.id)
    setCachedResult(entry)
    setPrefillQuestion(entry.question)
    setCurrentQuestion(entry.question)
    setHistoryOpen(false)
  }

  // ── Chip click: submit example question right away ──────────────────────
  const handleChipClick = (question: string) => {
    const provider = lastMeta?.provider ?? providers[0]?.id ?? ''
    const model    = lastMeta?.model    ?? providers[0]?.models[0] ?? ''
    setPrefillQuestion(question)
    handleSubmit(question, provider, model)
  }

  // ── Dual display path ───────────────────────────────────────────────────
  const sparqlToShow =
    cachedResult?.sparql ??
    (state.status === 'streaming' || state.status === 'done'
      ? state.sparql
      : state.status === 'error'
      ? state.sparql
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

  // Provider·model label shown in topbar
  const activeProvider = lastMeta
    ? `${lastMeta.provider} · ${lastMeta.model}`
    : providers[0]
    ? `${providers[0].id} · ${providers[0].models[0] ?? ''}`
    : ''

  const queryIsActive = state.status !== 'idle' || cachedResult !== null

  return (
    <div className="app-frame">

      {/* ── Left rail ── */}
      <aside className="app-rail" aria-label="Πλαϊνή γραμμή">
        <div className="rail-logo" aria-hidden="true"> <img src="/eudoxus-logo.svg" alt="Eudoxus Logo" /> </div>
        <button
          className={`rail-btn${view === 'query' ? ' active' : ''}`}
          onClick={() => setView('query')}
          title={t.tabQuery}
          aria-label={t.tabQuery}
          aria-current={view === 'query' ? 'page' : undefined}
        >
          { /* query icon */ }
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 600 }}>{ '{}' }</span>
        </button>
        <button
          className={`rail-btn${view === 'ontology' ? ' active' : ''}`}
          onClick={() => setView('ontology')}
          title={t.tabOntology}
          aria-label={t.tabOntology}
          aria-current={view === 'ontology' ? 'page' : undefined}
        >
          {/* ontology icon */}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>🕮</span>
        </button>
        <button
          className={`rail-btn${historyOpen ? ' active' : ''}`}
          onClick={() => setHistoryOpen(p => !p)}
          title={t.tabHistory}
          aria-label={t.tabHistory}
          aria-expanded={historyOpen}
        >
          {/* history icon */}
          <span style={{ fontSize: 16 }}>⟳</span>
        </button>
        {/* Theme toggle at the bottom */}
        <button
          className="rail-btn bottom"
          onClick={toggleTheme}
          title={theme === 'dark' ? t.switchToLight : t.switchToDark}
          aria-label={theme === 'dark' ? t.switchToLight : t.switchToDark}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </aside>

      {/* ── History drawer overlay ── */}
      <div
        className={`sidebar-overlay${historyOpen ? ' open' : ''}`}
        onClick={() => setHistoryOpen(false)}
        aria-modal={historyOpen}
        role={historyOpen ? 'dialog' : undefined}
        aria-label="Ιστορικό ερωτημάτων"
      >
        <div className="sidebar-overlay-panel" onClick={e => e.stopPropagation()}>
          <HistorySidebar
            entries={entries}
            activeId={activeHistoryId}
            onSelect={handleHistorySelect}
            onClear={clearHistory}
            onClose={() => setHistoryOpen(false)}
          />
        </div>
      </div>

      {/* ── Main column ── */}
      <div className="app-main">

        {/* ── Topbar ── */}
        <header className="app-header">
          <div className="header-left">
            <div className="header-brand">
              <span className="header-title">evdograph</span>
              <span className="header-version"></span>
            </div>
            <nav className="header-tabs" aria-label="Κύρια πλοήγηση">
              <button
                className={`header-tab${view === 'query' ? ' active' : ''}`}
                onClick={() => setView('query')}
                aria-current={view === 'query' ? 'page' : undefined}
              >
                {t.tabQuery}
              </button>
              <button
                className={`header-tab${view === 'ontology' ? ' active' : ''}`}
                onClick={() => setView('ontology')}
                aria-current={view === 'ontology' ? 'page' : undefined}
              >
                {t.tabOntology}
              </button>
              <button
                className={`header-tab${historyOpen ? ' active' : ''}`}
                onClick={() => setHistoryOpen(p => !p)}
                aria-expanded={historyOpen}
              >
                {t.tabHistory}
                {entries.length > 0 && (
                  <span className="tab-badge">{entries.length}</span>
                )}
              </button>
            </nav>
          </div>

          <div className="header-meta">
            {/* {activeProvider && (
              <span className="header-provider">{activeProvider}</span>
            )} */}
            {/* <div className="header-graphdb">
              <span className="live-dot" aria-hidden="true" />
              {t.graphdbConnected}
            </div> */}
            <button
              className="theme-toggle"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? t.switchToLight : t.switchToDark}
            >
              {theme === 'dark' ? '☀' : '☾'}
            </button>
          </div>
        </header>

        {/* ── ΟΝΤΟΛΟΓΙΑ view ── */}
        {view === 'ontology' && <OntologyPage />}

        {/* ── ΕΡΩΤΗΜΑ view ── */}
        {view === 'query' && (
          <>
            {/* ── Hero ── */}
            <section className="hero" aria-label="Αναζήτηση">
              <p className="hero-eyebrow" aria-hidden="true">{t.heroEyebrow}</p>
              <h1 className="hero-title">{t.heroTitle}</h1>

              <QueryForm
                providers={providers}
                disabled={state.status === 'streaming'}
                onSubmit={handleSubmit}
                prefillQuestion={prefillQuestion}
                showClear={queryIsActive}
                onClear={handleClear}
                // gitSha={GIT_SHA}
              />

              <div className="hero-chips" role="list" aria-label={t.heroTryLabel}>
                <span className="hero-chips-label">{t.heroTryLabel}</span>
                {t.heroChips.map(chip => (
                  <button
                    key={chip}
                    className="hero-chip"
                    role="listitem"
                    onClick={() => handleChipClick(chip)}
                    type="button"
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </section>

            {/* ── Content area ── */}
            <div className="content-wrap">

              {/* Question echo */}
              {queryIsActive && currentQuestion && (
                <div className="question-echo">
                  <span className="question-echo-label">{t.questionEchoLabel}</span>
                  <span className="question-echo-text">«{currentQuestion}»</span>
                </div>
              )}

              {/* SPARQL panel — key remounts on each new query to reset collapsed state */}
              {showSparqlPanel && (
                <SparqlPanel
                  key={submissionCount}
                  sparql={sparqlToShow ?? ''}
                  streaming={state.status === 'streaming' && !state.rerun}
                  executing={state.status === 'streaming' && !!state.executing}
                  onRerun={handleRerun}
                />
              )}

              {/* Results table (live or cached) */}
              {displayColumns && displayRows && displayTokenInfo && (
                <ResultsTable
                  columns={displayColumns}
                  rows={displayRows}
                  inputTokens={displayTokenInfo.inputTokens}
                  outputTokens={displayTokenInfo.outputTokens}
                  retries={displayTokenInfo.retries}
                  isCached={!!cachedResult}
                  onExampleSelect={(question: string) => {
                    const provider = lastMeta?.provider ?? providers[0]?.id ?? ''
                    const model    = lastMeta?.model    ?? providers[0]?.models[0] ?? ''
                    setPrefillQuestion(question)
                    handleSubmit(question, provider, model)
                  }}
                />
              )}

              {/* Error banner — suppressed when showing a cached history entry */}
              {!cachedResult && state.status === 'error' && (
                <ErrorBanner message={state.message} onDismiss={dismissError} />
              )}

            </div>
          </>
        )}

      </div>
    </div>
  )
}
