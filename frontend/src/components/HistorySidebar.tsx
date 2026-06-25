/**
 * HistorySidebar — history drawer panel (Console theme, ADR-016).
 *
 * Renders inside the overlay div in App.tsx. Props:
 *   entries    — all history entries (newest first, max 20)
 *   activeId   — UUID of the currently displayed cached result
 *   onSelect   — called when the user clicks an entry
 *   onClear    — called when the user clicks the footer clear button
 *   onClose    — called when the ✕ button is clicked
 *
 * Local state:
 *   search     — text filter (substring match on question)
 *   filter     — 'all' | 'success' | 'error' filter chip
 *
 * Entry meta: relative time + provider·model + row-count or σφάλμα badge.
 */

import { useState } from 'react'
import { t } from '../i18n/el'
import type { HistoryEntry } from '../types'

type Filter = 'all' | 'success' | 'error'

type Props = {
  entries: HistoryEntry[]
  activeId: string | null
  onSelect: (entry: HistoryEntry) => void
  onClear: () => void
  onClose: () => void
}

/** Format a Unix timestamp as a relative time string (e.g. "πριν 3 λεπτά"). */
function relativeTime(ts: number): string {
  const diffMs = Date.now() - ts
  const diffMin = Math.floor(diffMs / 60_000)
  const diffH   = Math.floor(diffMs / 3_600_000)
  if (diffMin < 1)  return 'μόλις τώρα'
  if (diffMin < 60) return `πριν ${diffMin} λεπτ${diffMin === 1 ? 'ό' : 'ά'}`
  if (diffH < 24)   return `πριν ${diffH} ώρ${diffH === 1 ? 'α' : 'ες'}`
  return new Date(ts).toLocaleDateString('el-GR', { day: '2-digit', month: 'short' })
}

export function HistorySidebar({ entries, activeId, onSelect, onClear, onClose }: Props) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  const filtered = entries
    .filter(e => {
      if (filter === 'success' && e.error) return false
      if (filter === 'error'   && !e.error) return false
      return true
    })
    .filter(e =>
      !search.trim() || e.question.toLowerCase().includes(search.toLowerCase())
    )

  return (
    <>
      {/* ── Drawer header ── */}
      <div className="sidebar-drawer-head">
        <div className="sidebar-drawer-title">
          <span className="sidebar-drawer-label">{t.tabHistory}</span>
          {entries.length > 0 && (
            <span className="sidebar-badge">{entries.length}</span>
          )}
        </div>
        <button
          className="sidebar-close"
          onClick={onClose}
          type="button"
          aria-label="Κλείσιμο ιστορικού"
        >
          ✕
        </button>
      </div>

      {/* ── Search ── */}
      <div className="sidebar-search-wrap">
        <div className="sidebar-search-inner">
          <span className="sidebar-search-icon" aria-hidden="true">⌕</span>
          <input
            className="sidebar-search"
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t.historySearchPlaceholder}
            aria-label={t.historySearchPlaceholder}
          />
        </div>
      </div>

      {/* ── Filter chips ── */}
      <div className="sidebar-filters" role="group" aria-label="Φίλτρο ιστορικού">
        {(['all', 'success', 'error'] as Filter[]).map(f => (
          <button
            key={f}
            className={`sidebar-filter-chip${filter === f ? ' active' : ''}`}
            onClick={() => setFilter(f)}
            type="button"
            aria-pressed={filter === f}
          >
            {f === 'all'     ? t.historyFilterAll
            : f === 'success' ? t.historyFilterSuccess
            : t.historyFilterError}
          </button>
        ))}
      </div>

      {/* ── Entry list ── */}
      <div className="sidebar-list" role="list">
        {filtered.length === 0 ? (
          <p className="sidebar-empty">{t.historyEmpty}</p>
        ) : (
          filtered.map(entry => (
            <div
              key={entry.id}
              className={`sidebar-item${entry.id === activeId ? ' active' : ''}`}
              onClick={() => onSelect(entry)}
              role="listitem"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && onSelect(entry)}
              aria-current={entry.id === activeId ? 'true' : undefined}
            >
              <div className="sidebar-item-meta-row">
                <span className="sidebar-item-meta">
                  {relativeTime(entry.timestamp)} · {entry.provider} · {entry.model}
                </span>
                {entry.error
                  ? <span className="sidebar-item-badge error">{t.historyFilterError}</span>
                  : entry.rows.length === 0
                  ? <span className="sidebar-item-badge empty">0 γραμμές</span>
                  : <span className="sidebar-item-badge success">{entry.rows.length} γραμμές</span>
                }
              </div>
              <div className="sidebar-item-question">
                <span className="q-arrow" aria-hidden="true">› </span>
                {entry.question}
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Footer ── */}
      {entries.length > 0 && (
        <div className="sidebar-footer">
          <button className="sidebar-clear-btn" onClick={onClear} type="button">
            ✕ {t.historyClear}
          </button>
        </div>
      )}
    </>
  )
}
