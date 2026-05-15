/**
 * EmptyState — shown inside the results panel when a query returns zero rows.
 *
 * The three example queries are defined in i18n/el.ts (noResultsExamples).
 * Clicking one fires onExampleSelect which bubbles up to App.tsx, where it
 * pre-fills the input and submits a new query automatically.
 */

import { t } from '../../i18n/el'

type Props = {
  onExampleSelect: (question: string) => void
}

export function EmptyState({ onExampleSelect }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-title">{t.noResultsTitle}</div>
      <p className="empty-body">{t.noResultsBody}</p>
      <ul className="empty-examples" aria-label="Παραδείγματα ερωτημάτων">
        {t.noResultsExamples.map((ex, i) => (
          <li key={i}>
            {/* Using <span role="button"> instead of <button> to avoid the browser's
                default button styling inside a <ul>. Keyboard (Enter) is also wired. */}
            <span
              className="empty-example-item"
              role="button"
              tabIndex={0}
              onClick={() => onExampleSelect(ex)}
              onKeyDown={e => e.key === 'Enter' && onExampleSelect(ex)}
            >
              <span className="example-pfx" aria-hidden="true">›</span>
              {ex}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
