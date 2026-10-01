/**
 * BooleanAnswer — the results panel's body for a yes/no question (ADR-037).
 *
 * Shown instead of the table when the backend returns `boolean` (the query was
 * an ASK). A one-cell table reading "answer / false" means little to the
 * students and researchers this UI is for, so the answer is a large «Ναι» /
 * «Όχι» with a small note on where it comes from. The header (count, tokens,
 * export) stays as for any result — export still writes the `answer` row.
 */

import { t } from '../../i18n/el'
import { booleanAnswerText } from '../../utils/answer'

type Props = {
  value: boolean
}

export function BooleanAnswer({ value }: Props) {
  return (
    <div className="boolean-answer" role="status" aria-live="polite">
      <div className="boolean-answer-label">{t.answerLabel}</div>
      <div className={`boolean-answer-value ${value ? 'is-yes' : 'is-no'}`}>
        {booleanAnswerText(value)}
      </div>
      <div className="boolean-answer-hint">{t.answerHint}</div>
    </div>
  )
}
