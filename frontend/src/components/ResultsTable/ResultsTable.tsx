/**
 * ResultsTable — orchestrates sorting, pagination, column visibility, and export.
 *
 * This is the most complex component in the app. It owns the table's local state
 * and delegates rendering to focused child components:
 *   - useSortedPaged  →  sort + pagination logic (pure hook)
 *   - SortIcon        →  column header sort indicator
 *   - Pagination      →  prev/next/numbered page buttons + rows-per-page selector
 *   - ColumnsMenu     →  show/hide individual columns
 *   - ExportMenu      →  download all rows as CSV/JSON/XML/TSV
 *   - EmptyState      →  shown when rows.length === 0
 */

import { useState, useEffect, useRef } from 'react'
import { t } from '../../i18n/el'
import { SortIcon } from '../SortIcon'
import { Pagination } from './Pagination'
import { ColumnsMenu } from './ColumnsMenu'
import { ExportMenu } from './ExportMenu'
import { EmptyState } from './EmptyState'
import { useSortedPaged } from '../../hooks/useSortedPaged'
import type { SortState, ColumnVisibility } from '../../types'

type Row = Record<string, string | undefined>

type Props = {
  columns: string[]
  rows: Row[]
  inputTokens: number
  outputTokens: number
  retries: number
  isCached: boolean      // shows the "(αποθηκευμένο)" badge when viewing a history entry
  onExampleSelect: (question: string) => void // called by EmptyState example clicks
}

const DEFAULT_PAGE_SIZE = 10

export function ResultsTable({
  columns,
  rows,
  inputTokens,
  outputTokens,
  retries,
  isCached,
  onExampleSelect,
}: Props) {
  const [sortState, setSortState] = useState<SortState>({ column: null, direction: 'idle' })
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [visibility, setVisibility] = useState<ColumnVisibility>({})
  const [showColumns, setShowColumns] = useState(false)
  const [showExport, setShowExport] = useState(false)

  // Refs let us detect outside-clicks to close dropdowns without adding global listeners
  // in a way that would fight with React's synthetic event system.
  const columnsMenuRef = useRef<HTMLDivElement>(null)
  const exportMenuRef = useRef<HTMLDivElement>(null)

  // Reset everything when a new result set arrives (columns array reference changes).
  // This fires on every new query so the table always starts at page 1, unsorted,
  // with all columns visible.
  useEffect(() => {
    setSortState({ column: null, direction: 'idle' })
    setPageIndex(0)
    setVisibility({})
  }, [columns])

  // Close whichever dropdown is open when the user clicks anywhere outside it.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (columnsMenuRef.current && !columnsMenuRef.current.contains(e.target as Node)) {
        setShowColumns(false)
      }
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setShowExport(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSort = (col: string) => {
    setSortState(prev => {
      // Clicking a new column always starts at asc.
      if (prev.column !== col) return { column: col, direction: 'asc' }
      // Cycling the same column: idle → asc → desc → idle.
      const next = prev.direction === 'idle' ? 'asc'
        : prev.direction === 'asc' ? 'desc'
        : 'idle'
      return { column: next === 'idle' ? null : col, direction: next }
    })
    setPageIndex(0) // always go back to page 1 after re-sorting
  }

  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setPageIndex(0) // reset to page 1 so the user isn't on a page that no longer exists
  }

  const toggleColumn = (col: string) => {
    // Flip the column's visibility. Absence = visible, so we store explicit booleans.
    setVisibility(prev => ({ ...prev, [col]: prev[col] === false ? true : false }))
  }

  // Only render the columns that aren't explicitly hidden.
  const visibleColumns = columns.filter(c => visibility[c] !== false)

  // useSortedPaged handles sorting + page slicing via useMemo — no recalculation
  // unless rows, sortState, pageSize, or pageIndex actually change.
  const { visibleRows, totalPages } = useSortedPaged(rows, sortState, pageSize, pageIndex)

  return (
    <div className="panel">
      {/* ── Results header: row count, token usage, action buttons ── */}
      <div className="results-head">
        <div className="results-meta">
          <span className="results-count">{rows.length}{" " + t.resultsLabel}</span>
          {' ' + inputTokens} in · {outputTokens} out tokens
          {retries > 0 && ` · ${retries} retries`}
          {isCached && (
            <span className="cached-badge" style={{ marginLeft: 8 }}>{t.cachedBadge}</span>
          )}
        </div>

        <div className="results-actions">
          {/* Columns menu: ref wrapper lets us detect outside clicks to close it. */}
          <div ref={columnsMenuRef} style={{ position: 'relative' }}>
            <button
              className="panel-btn"
              type="button"
              onClick={() => { setShowColumns(p => !p); setShowExport(false) }}
              aria-expanded={showColumns}
            >
              {t.columnsLabel}
            </button>
            {showColumns && (
              <ColumnsMenu columns={columns} visibility={visibility} onToggle={toggleColumn} />
            )}
          </div>

          {/* Export menu: receives the full `rows` array (not just the current page). */}
          <div ref={exportMenuRef} style={{ position: 'relative' }}>
            <button
              className="panel-btn"
              type="button"
              onClick={() => { setShowExport(p => !p); setShowColumns(false) }}
              aria-expanded={showExport}
            >
              {t.exportLabel}
            </button>
            {showExport && (
              <ExportMenu columns={columns} rows={rows} />
            )}
          </div>
        </div>
      </div>

      {/* ── Table or empty state ── */}
      {rows.length === 0 ? (
        <EmptyState onExampleSelect={onExampleSelect} />
      ) : (
        <>
          {/* overflow-x: auto in CSS handles wide tables on small screens. */}
          <div className="table-scroll">
            <table className="results-table">
              <thead>
                <tr>
                  {visibleColumns.map(col => (
                    <th
                      key={col}
                      onClick={() => handleSort(col)}
                      aria-sort={
                        sortState.column === col
                          ? sortState.direction === 'asc' ? 'ascending' : 'descending'
                          : 'none'
                      }
                    >
                      <div className="th-inner">
                        {col}
                        {/* Show the active sort direction for this column, idle otherwise. */}
                        <SortIcon
                          direction={sortState.column === col ? sortState.direction : 'idle'}
                        />
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* visibleRows is the current-page slice from useSortedPaged. */}
                {visibleRows.map((row, i) => (
                  // SPARQL rows have no stable identifier; positional index is intentional.
                  <tr key={i}>
                    {visibleColumns.map(col => (
                      // ?? '' prevents the literal string "undefined" from appearing in cells.
                      <td key={col}>{row[col] ?? ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            pageIndex={pageIndex}
            totalPages={totalPages}
            pageSize={pageSize}
            onPageChange={setPageIndex}
            onPageSizeChange={handlePageSizeChange}
          />
        </>
      )}
    </div>
  )
}
