/**
 * Yes/no answers — the result of a SPARQL ASK query (ADR-037).
 *
 * The backend sends an ASK answer twice: as `boolean` (true/false) and as a
 * one-row table `answer: "true" | "false"` (so export and history work as for
 * any result). The results panel shows `boolean` as «Ναι» / «Όχι»; `null`
 * (a SELECT result) or `undefined` (a history entry saved before ADR-037)
 * means "show the table as usual".
 */

import { t } from '../i18n/el'

/** True only for a real yes/no answer — not for SELECT results (null) or old history entries. */
export function isBooleanResult(value: boolean | null | undefined): value is boolean {
  return typeof value === 'boolean'
}

/** The Greek word shown for a yes/no answer. */
export function booleanAnswerText(value: boolean): string {
  return value ? t.answerYes : t.answerNo
}
