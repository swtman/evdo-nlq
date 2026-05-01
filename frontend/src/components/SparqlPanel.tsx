import { useState } from 'react'
import { t } from '../i18n/el'

type Props = {
  /** The SPARQL string accumulated so far (may be partial while streaming). */
  sparql: string
  /** True while the backend SSE stream is still open. */
  streaming: boolean
}

/**
 * SparqlPanel — collapsible panel that displays the generated SPARQL query.
 *
 * Renders nothing until there is content or the stream has started, so it
 * stays invisible in the initial idle state.  A blinking cursor (`▌`) is
 * appended to the code block while streaming to give live feedback.
 *
 * The collapse toggle is purely local state — it persists across re-renders
 * within the same query session but resets on the next submit because the
 * parent re-mounts the component (or the user can re-expand manually).
 */
export function SparqlPanel({ sparql, streaming }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  // Nothing to show yet — stay invisible until streaming begins or SPARQL arrives.
  if (!sparql && !streaming) return null

  return (
    <div className="panel panel--emerald">
      <div className="panel-header">
        <div className="sparql-header-left">
          <span className="panel-label panel-label--emerald">{t.sparqlLabel}</span>
          {streaming
            ? <span className="status-pill status-pill--generating">{t.sparqlGenerating}</span>
            : <span className="status-pill status-pill--complete">{t.sparqlComplete}</span>
          }
        </div>
        <button
          className="collapse-btn"
          onClick={() => setCollapsed(c => !c)}
          aria-expanded={!collapsed}
          type="button"
        >
          {collapsed ? t.sparqlExpand : t.sparqlCollapse}
        </button>
      </div>
      {!collapsed && (
        <pre className="sparql-code">
          {sparql}
          {streaming && <span className="cursor">▌</span>}
        </pre>
      )}
    </div>
  )
}
