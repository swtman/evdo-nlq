/**
 * HistorySidebar — the query history overlay panel.
 *
 * Renders inside the overlay div in App.tsx. All state (which entries exist,
 * which is active) is owned by App and passed down as props — this component
 * is intentionally "dumb" (no data-fetching, no localStorage access).
 */

import { useState } from 'react'
import { t } from '../i18n/el'
import type { HistoryEntry } from '../types'

type Props = {
  entries: HistoryEntry[]  // newest first, max 20 (enforced by useHistory)
  activeId: string | null  // UUID of the currently displayed cached result
  onSelect: (entry: HistoryEntry) => void
  onClear: () => void
}

/** Format a Unix timestamp as "HH:mm" in Greek locale (e.g. "14:32 μ.μ."). */
function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('el-GR', { hour: '2-digit', minute: '2-digit' })
}

/** Build the one-line meta string shown above each question (time + row count or error). */
function itemMeta(entry: HistoryEntry): string {
  const time = formatTime(entry.timestamp)
  if (entry.error) return `${time} · ${t.historyError} ✕`
  return `${time} · ${entry.rows.length} rows`
}

export function HistorySidebar({ entries, activeId, onSelect, onClear }: Props) {
  // Local search state — filters the list by NL question substring, client-side only.
  const [search, setSearch] = useState('')

  const filtered = search.trim()
    ? entries.filter(e => e.question.toLowerCase().includes(search.toLowerCase()))
    : entries

  return (
    <>
      <div className="sidebar-label">{t.historyLabel}</div>

      <input
        className="sidebar-search"
        type="text"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder={t.historySearchPlaceholder}
        aria-label={t.historySearchPlaceholder}
      />

      <div className="sidebar-list">
        {filtered.length === 0 ? (
          <p className="sidebar-empty">{t.historyEmpty}</p>
        ) : (
          filtered.map(entry => (
            <div
              key={entry.id}
              // 'active' class adds the burnt-orange left border for the current entry.
              className={`sidebar-item${entry.id === activeId ? ' active' : ''}`}
              onClick={() => onSelect(entry)}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && onSelect(entry)}
            >
              <div className="sidebar-item-meta">{itemMeta(entry)}</div>
              {/* -webkit-line-clamp in CSS truncates long questions to 2 lines. */}
              <div className="sidebar-item-question">{entry.question}</div>
            </div>
          ))
        )}
      </div>

      {/* Only render the clear button when there's something to clear. */}
      {entries.length > 0 && (
        <button className="sidebar-footer" onClick={onClear} type="button">
          {t.historyClear}
        </button>
      )}
    </>
  )
}
