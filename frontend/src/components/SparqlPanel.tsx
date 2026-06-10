import { useState } from 'react'
import { t } from '../i18n/el'

type Props = {
  sparql: string
  streaming: boolean
  executing: boolean
  /** Optional callback — when provided an "Edit" button appears after the query
   *  is ready. Clicking it enters edit mode; clicking "Rerun" calls this with
   *  the (possibly modified) SPARQL string so the caller can bypass the LLM and
   *  execute it directly against GraphDB. */
  onRerun?: (editedSparql: string) => void
}

/**
 * SparqlPanel — collapsible panel for the generated SPARQL query.
 *
 * Shows `// generating…` with a pulsing square while streaming, and `// ready`
 * when complete. Copy button toggles to `✓ copied` for 1.5s on click.
 * A thin animated progress bar appears while GraphDB is executing.
 *
 * Edit mode (requires `onRerun` prop):
 *   - An "Edit" button appears once the query is ready and not executing.
 *   - Clicking it switches the read-only `<pre>` to an editable `<textarea>`.
 *   - Header actions swap to Cancel + Rerun.
 *   - Clicking Rerun calls `onRerun(draft)` with the (possibly changed) SPARQL.
 *   - Clicking Cancel discards edits and returns to read-only view.
 */
export function SparqlPanel({ sparql, streaming, executing, onRerun }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  if (!sparql && !streaming) return null

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(sparql)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API unavailable (non-HTTPS or permissions denied).
    }
  }

  const handleEdit = () => {
    setDraft(sparql)
    setEditing(true)
  }

  const handleCancel = () => {
    setEditing(false)
    setDraft('')
  }

  const handleRerun = () => {
    if (!draft.trim() || !onRerun) return
    setEditing(false)
    setDraft('')
    onRerun(draft)
  }

  // Whether to show the "Edit" button: only after streaming/executing are done
  // and only when the caller has provided the onRerun callback.
  const canEdit = !streaming && !executing && !!sparql && !!onRerun

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="sparql-label-group">
          <span className="panel-label">{t.sparqlLabel}</span>
          <span className="sparql-status">
            {streaming
              ? <><span className="live-square" aria-hidden="true" />{t.sparqlGenerating}</>
              : t.sparqlComplete
            }
          </span>
        </div>
        <div className="panel-actions">
          {editing ? (
            /* Edit mode: show Cancel and Rerun in place of normal actions */
            <>
              <button
                className="panel-btn"
                onClick={handleCancel}
                type="button"
                aria-label={t.sparqlCancel}
              >
                {t.sparqlCancel}
              </button>
              <button
                className="panel-btn"
                onClick={handleRerun}
                type="button"
                disabled={!draft.trim()}
                aria-label={t.sparqlRerun}
              >
                {t.sparqlRerun}
              </button>
            </>
          ) : (
            /* Read-only mode: Copy, optional Edit, then collapse toggle */
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
                <button
                  className="panel-btn"
                  onClick={handleEdit}
                  type="button"
                  aria-label={t.sparqlEdit}
                >
                  {t.sparqlEdit}
                </button>
              )}
              <button
                className="panel-btn"
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

      {!collapsed && (
        editing ? (
          /* Editable textarea — same mono font and panel styling as .sparql-code */
          <textarea
            className="sparql-editor"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            spellCheck={false}
            aria-label="SPARQL editor"
            autoFocus
          />
        ) : (
          <pre className="sparql-code">
            {sparql}
            {streaming && <span className="cursor" aria-hidden="true">▌</span>}
          </pre>
        )
      )}

      {executing && (
        <div className="graphdb-bar" role="status" aria-live="polite">
          <span className="bar-prefix" aria-hidden="true">›</span>
          <span>{t.graphdbExecuting}</span>
          <div className="graphdb-progress" aria-hidden="true">
            <div className="graphdb-sweep" />
          </div>
        </div>
      )}
    </div>
  )
}
