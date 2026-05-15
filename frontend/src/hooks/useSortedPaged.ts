/**
 * Pure memoised hook: sorts a row array by one column, then slices to the current page.
 * Lives here (not in ResultsTable) so the logic can be tested independently.
 */

import { useMemo } from 'react'
import type { SortState } from '../types'

type Row = Record<string, string | undefined>

/**
 * Compare two cell values for sorting.
 * If both values look like numbers, compare numerically (so "10" sorts after "9").
 * Otherwise compare as Greek-locale strings (case-insensitive, accent-insensitive).
 */
function compareValues(a: string | undefined, b: string | undefined): number {
  const av = a ?? ''
  const bv = b ?? ''
  const an = Number(av)
  const bn = Number(bv)
  // Numeric-aware: "2" < "10" (not "10" < "2" as in lexicographic order)
  if (!isNaN(an) && !isNaN(bn)) return an - bn
  return av.localeCompare(bv, 'el', { sensitivity: 'base' })
}

/**
 * Sort and paginate a flat row array.
 *
 * Sort is row-coherent: the entire Row object moves as a unit, so column values
 * always stay with their row — only the order of rows changes.
 *
 * @param rows       Full result set from the backend (not paginated).
 * @param sortState  Which column to sort by and in which direction.
 * @param pageSize   How many rows to show per page (10 / 25 / 50 / 100).
 * @param pageIndex  Zero-based current page index.
 * @returns          The slice of rows for the current page, and total page count.
 */
export function useSortedPaged(
  rows: Row[],
  sortState: SortState,
  pageSize: number,
  pageIndex: number,
): { visibleRows: Row[]; totalPages: number } {
  // Only re-sort when rows or sortState actually change.
  const sorted = useMemo(() => {
    if (sortState.direction === 'idle' || !sortState.column) return rows
    const col = sortState.column
    const factor = sortState.direction === 'asc' ? 1 : -1
    // Spread into a new array first — Array.sort() mutates in place.
    return [...rows].sort((a, b) => compareValues(a[col], b[col]) * factor)
  }, [rows, sortState])

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize))
  // Guard against a stale pageIndex that exceeds the new total (e.g. after page-size change).
  const safePage = Math.min(pageIndex, totalPages - 1)
  const start = safePage * pageSize
  const visibleRows = sorted.slice(start, start + pageSize)

  return { visibleRows, totalPages }
}
