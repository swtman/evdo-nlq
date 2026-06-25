import { useState, useMemo, useLayoutEffect, useRef } from 'react'
import { t } from '../i18n/el'
import { highlightSparql } from '../utils/highlightSparql'

type Props = {
  sparql: string
  streaming: boolean
  executing: boolean
  /** When provided, an "Edit" button appears; clicking Rerun calls this with the edited SPARQL. */
  onRerun?: (editedSparql: string) => void
}

/**
 * SparqlPanel — terminal-style panel for the generated SPARQL query (ADR-016).
 *
 * Visual chrome: traffic-light dots, query.sparql filename, ready/streaming status.
 * Code area: line-number gutter + syntax-highlighted code when not streaming;
 * plain text + blinking cursor while streaming.
 * Footer: "// generated · tokens · valid ✓" meta line.
 * GraphDB bar: sweep animation while GraphDB is executing.
 *
 * Edit mode (requires onRerun prop):
 *   - "Edit" button appears once ready and not executing.
 *   - The terminal panel stays intact; the <pre> is replaced by an editable
 *     <textarea> that sits in the same position, preserving the gutter and chrome.
 *   - The panel root gains the "editing" class, triggering an accent highlight.
 *   - Line numbers update live from the draft text.
 *   - Cancel/Rerun replace the normal actions. Rerun forwards the edited text to
 *     the caller verbatim — no LLM, no SPARQL parsing/transformation.
 */
export function SparqlPanel({ sparql, streaming, executing, onRerun }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  /** Ref used to auto-grow the inline editor to fit its content. */
  const draftRef = useRef<HTMLTextAreaElement>(null)

  if (!sparql && !streaming) return null

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(sparql)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API unavailable.
    }
  }

  const handleEdit = () => { setDraft(sparql); setEditing(true) }
  const handleCancel = () => { setEditing(false); setDraft('') }
  const handleRerun = () => {
    if (!draft.trim() || !onRerun) return
    setEditing(false); setDraft('')
    onRerun(draft)
  }

  const canEdit = !streaming && !executing && !!sparql && !!onRerun

  // Line numbers: use the draft while editing so gutter tracks live changes.
  const activeText = editing ? draft : sparql
  const lineCount = activeText ? activeText.split('\n').length : 1
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => i + 1).join('\n')

  // Syntax-highlighted tokens — memoised so they don't recompute on every keystroke.
  // Not computed while streaming (plain text + cursor is shown instead).
  const tokens = useMemo(
    () => (!streaming && sparql ? highlightSparql(sparql) : null),
    [sparql, streaming],
  )

  // Auto-grow the inline editor whenever the draft changes.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useLayoutEffect(() => {
    const el = draftRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  }, [draft])

  return (
    <div className={`panel${editing ? ' editing' : ''}`}>
      {/* ── Terminal header ── */}
      <div className="sparql-terminal-head">
        <div className="sparql-head-left">
          <div className="sparql-traffic-lights" aria-hidden="true">
            <span className="sparql-traffic-light" />
            <span className="sparql-traffic-light" />
            <span className="sparql-traffic-light active" />
          </div>
          <span className="sparql-filename">{t.sparqlFilename}</span>
          <span className="sparql-status">
            {streaming
              ? <><span className="live-square" aria-hidden="true" />{t.sparqlGenerating}</>
              : <><span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block', marginRight: 5 }} aria-hidden="true" />{t.sparqlReady}</>
            }
          </span>
        </div>

        <div className="panel-actions">
          {editing ? (
            <>
              <button className="panel-btn" onClick={handleCancel} type="button" aria-label={t.sparqlCancel}>
                {t.sparqlCancel}
              </button>
              <button
                className="panel-btn"
                onClick={handleRerun}
                type="button"
                disabled={!draft.trim()}
                style={{ background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none' }}
                aria-label={t.sparqlRerun}
              >
                {t.sparqlRerun}
              </button>
            </>
          ) : (
            <>
              {!streaming && sparql && (
                <button
                  className={`panel-btn${copied ? ' copied' : ''}`}
                  onClick={handleCopy}
                  type="button"
                  aria-label={t.sparqlCopy}
                >
                  {copied ? t.sparqlCopied : t.sparqlCopy}
                </button>
              )}
              {canEdit && (
                <button className="panel-btn" onClick={handleEdit} type="button" aria-label={t.sparqlEdit}>
                  {t.sparqlEdit}
                </button>
              )}
              <button
                className="panel-btn"
                style={{ background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none' }}
                onClick={() => setCollapsed(c => !c)}
                aria-expanded={!collapsed}
                type="button"
              >
                {collapsed ? t.sparqlShow : t.sparqlHide}
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Code body ── */}
      {!collapsed && (
        <div className="sparql-terminal-body">
          {/* Line-number gutter — tracks the draft live in edit mode */}
          <div className="sparql-gutter" aria-hidden="true">{lineNumbers}</div>

          {editing ? (
            /* Inline editor: sits where the <pre> normally lives, same font/spacing */
            <textarea
              ref={draftRef}
              className="sparql-editor"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              spellCheck={false}
              aria-label="SPARQL editor"
              autoFocus
            />
          ) : (
            /* Code — highlighted when ready, plain + cursor while streaming */
            <pre className="sparql-code">
              {streaming || !tokens
                ? (
                    <>
                      {sparql}
                      {streaming && <span className="cursor" aria-hidden="true">▌</span>}
                    </>
                  )
                : tokens.map((tok, i) =>
                    tok.cls
                      ? <span key={i} className={`sparql-${tok.cls}`}>{tok.text}</span>
                      : tok.text
                  )
              }
            </pre>
          )}
        </div>
      )}

      {/* ── Footer meta line ── */}
      {!collapsed && !streaming && !editing && sparql && (
        <div className="sparql-terminal-footer">
          <span style={{ color: 'var(--accent)' }}>// </span>
          {t.sparqlComplete} · έγκυρο ✓
        </div>
      )}

      {/* ── GraphDB executing bar ── */}
      {executing && (
        <div className="graphdb-bar" role="status" aria-live="polite">
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'pulse 1.2s infinite', display: 'inline-block' }} aria-hidden="true" />
          {t.graphdbExecuting}
          <div className="graphdb-progress" aria-hidden="true">
            <div className="graphdb-sweep" />
          </div>
        </div>
      )}
    </div>
  )
}
