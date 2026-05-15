/**
 * ColumnsMenu — dropdown checklist for showing or hiding table columns.
 *
 * A missing key in `visibility` means "visible" (see ColumnVisibility in types.ts).
 * The parent (ResultsTable) resets visibility to {} on each new query, so all columns
 * are visible by default without any explicit initialization.
 */

import { t } from '../../i18n/el'
import type { ColumnVisibility } from '../../types'

type Props = {
  columns: string[]           // all columns in the current result set, in order
  visibility: ColumnVisibility
  onToggle: (col: string) => void
}

export function ColumnsMenu({ columns, visibility, onToggle }: Props) {
  return (
    <div className="dropdown-menu" role="menu" aria-label={t.columnsLabel}>
      <div className="dropdown-header">{t.columnsLabel}</div>
      {columns.map(col => {
        // Absence from the map = visible. Only `false` means hidden.
        const visible = visibility[col] !== false
        return (
          <div
            key={col}
            className="dropdown-item"
            role="menuitemcheckbox"
            aria-checked={visible}
            tabIndex={0}
            onClick={() => onToggle(col)}
            onKeyDown={e => e.key === 'Enter' && onToggle(col)}
          >
            {/* 'on' class fills the checkbox square with ink color. */}
            <span className={`col-check${visible ? ' on' : ''}`} aria-hidden="true">
              {visible ? '✓' : ''}
            </span>
            <span style={{ flex: 1, paddingLeft: 8 }}>{col}</span>
          </div>
        )
      })}
    </div>
  )
}
