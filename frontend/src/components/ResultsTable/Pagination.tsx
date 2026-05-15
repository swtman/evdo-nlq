/**
 * Pagination — row-count selector and numbered page buttons.
 *
 * All state (pageIndex, pageSize) lives in the parent (ResultsTable).
 * This component is purely presentational: it receives values and fires callbacks.
 */

import { t } from '../../i18n/el'

const PAGE_SIZES = [10, 25, 50, 100] // options shown in the rows-per-page selector

type Props = {
  pageIndex: number                       // zero-based current page
  totalPages: number                      // derived by useSortedPaged
  pageSize: number                        // rows per page
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

export function Pagination({ pageIndex, totalPages, pageSize, onPageChange, onPageSizeChange }: Props) {
  // Build a zero-based array [0, 1, 2, …, totalPages-1] for rendering numbered buttons.
  const pageNumbers = Array.from({ length: totalPages }, (_, i) => i)

  return (
    <div className="pagination">
      {/* Left side: rows-per-page selector */}
      <div className="page-size-group">
        <span>{t.pageRowsLabel}</span>
        <select
          className="page-size-select"
          value={pageSize}
          onChange={e => onPageSizeChange(Number(e.target.value))}
          aria-label={t.pageRowsLabel}
        >
          {PAGE_SIZES.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {/* Right side: prev, numbered pages, next */}
      <div className="page-nav" role="navigation" aria-label="Σελιδοποίηση">
        <button
          className="page-btn"
          onClick={() => onPageChange(pageIndex - 1)}
          disabled={pageIndex === 0} // no previous page on page 0
          aria-label={t.pagePrev}
        >
          {t.pagePrev}
        </button>

        {pageNumbers.map(p => (
          <button
            key={p}
            // 'active' class inverts the button to ink-on-paper for the current page.
            className={`page-btn${p === pageIndex ? ' active' : ''}`}
            onClick={() => onPageChange(p)}
            aria-current={p === pageIndex ? 'page' : undefined}
          >
            {p + 1} {/* display is 1-based even though pageIndex is 0-based */}
          </button>
        ))}

        <button
          className="page-btn"
          onClick={() => onPageChange(pageIndex + 1)}
          disabled={pageIndex >= totalPages - 1} // no next page on the last page
          aria-label={t.pageNext}
        >
          {t.pageNext}
        </button>
      </div>
    </div>
  )
}
