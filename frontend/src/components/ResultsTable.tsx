import { t } from '../i18n/el'

type Props = {
  columns: string[]
  /**
   * Rows from the backend.  Values are `string | undefined` because optional
   * SPARQL bindings may be absent for some rows.  Always use `row[col] ?? ''`
   * when rendering to avoid rendering "undefined" as text.
   */
  rows: Record<string, string | undefined>[]
  inputTokens: number
  outputTokens: number
  retries: number
}

/**
 * ResultsTable — displays the SPARQL query results in a scrollable table.
 *
 * Shows a "no results" message when the backend returns an empty row set.
 * Token usage and retry count are always shown in the footer so the user can
 * monitor cost and pipeline behaviour.
 */
export function ResultsTable({ columns, rows, inputTokens, outputTokens, retries }: Props) {
  return (
    <div className="panel panel--blue">
      <div className="panel-header">
        <span className="panel-label panel-label--blue">{t.resultsLabel}</span>
      </div>
      {rows.length === 0 ? (
        <p className="no-results">{t.noResults}</p>
      ) : (
        <div className="table-wrapper">
          <table className="results-table">
            <thead>
              <tr>
                {columns.map(col => <th key={col}>{col}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map(col => (
                    // Use nullish coalescing to render an empty cell when a
                    // SPARQL binding is absent rather than the string "undefined".
                    <td key={col}>{row[col] ?? ''}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="token-info">{t.tokenInfo(inputTokens, outputTokens, retries)}</p>
    </div>
  )
}
