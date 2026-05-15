import { useState } from 'react'
import { t } from '../i18n/el'

type Props = {
  sparql: string
  streaming: boolean
  executing: boolean
}

/**
 * SparqlPanel — collapsible panel for the generated SPARQL query.
 *
 * Shows `// generating…` with a pulsing square while streaming, and `// ready`
 * when complete. Copy button toggles to `✓ copied` for 1.5s on click.
 * A thin animated progress bar appears while GraphDB is executing.
 */
export function SparqlPanel({ sparql, streaming, executing }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [copied, setCopied] = useState(false)

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
          <button
            className="panel-btn"
            onClick={() => setCollapsed(c => !c)}
            aria-expanded={!collapsed}
            type="button"
          >
            {collapsed ? t.sparqlShow : t.sparqlHide}
          </button>
        </div>
      </div>

      {!collapsed && (
        <pre className="sparql-code">
          {sparql}
          {streaming && <span className="cursor" aria-hidden="true">▌</span>}
        </pre>
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
