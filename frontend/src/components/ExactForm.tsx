/**
 * ExactForm — the ΟΝΤΟΛΟΓΙΑ page's "exact KG form" (ADR-030, option C2).
 *
 * The page shows a tidied, readable name; a hand-written SPARQL query needs the
 * name EXACTLY as stored in the knowledge graph. They differ for 13,301 course,
 * 47 book and 6 department names — almost always by invisible whitespace (a
 * leading tab, a double space, a no-break space) — and a title may be stored in
 * several spellings (ALL-CAPS and mixed-case), all of which a query needs.
 *
 * So: every result keeps its readable line plus a ⧉ button that copies the exact
 * literal; a small «ακριβής μορφή στο γράφο» disclosure (native <details>, so it is
 * keyboard-accessible with no extra state) appears ONLY when the literal differs
 * from what is shown or several spellings exist. Inside it each literal is shown
 * in monospace with invisible characters drawn visibly, each with its own ⧉, plus
 * «αντιγραφή όλων» (one literal per line). No SPARQL is generated here — the
 * frontend never inlines SPARQL (frontend/CLAUDE.md).
 */

import { useEffect, useState, type ReactNode } from 'react'
import type { EntitySearchResult } from '../hooks/useEntitySearch'
import { t } from '../i18n/el'

/** Collapse whitespace the way the backend's display form does. */
function tidy(s: string): string {
  return s.split(/\s+/).filter(Boolean).join(' ')
}

/** The literal behind the displayed title (or the first one), for the main ⧉. */
export function primaryLiteral(r: EntitySearchResult): string {
  const literals = r.literals ?? []
  return literals.find(l => tidy(l) === r.title) ?? literals[0] ?? r.title
}

/** True when the exact form is worth showing: a different literal, or several spellings. */
export function exactFormNeeded(display: string, literals: string[]): boolean {
  return literals.length > 1 || (literals.length === 1 && literals[0] !== display)
}

/**
 * Draw invisible characters: tab ⇥, no-break space ⍽, any other unusual space •,
 * and every space that is leading, trailing or next to another space •.
 */
export function visibleWhitespace(s: string): { nodes: ReactNode[]; marked: boolean } {
  const chars = [...s]
  let marked = false
  const nodes = chars.map((ch, i) => {
    let mark: string | null = null
    if (ch === '\t') mark = '⇥'
    else if (ch === ' ') mark = '⍽'
    else if (ch !== ' ' && /\s/u.test(ch)) mark = '•'
    else if (ch === ' ') {
      const lonely = i > 0 && i < chars.length - 1 && chars[i - 1] !== ' ' && chars[i + 1] !== ' '
      if (!lonely) mark = '•'
    }
    if (mark === null) return ch
    marked = true
    return (
      <span key={i} className="od-ws-mark" aria-hidden="true">
        {mark}
      </span>
    )
  })
  return { nodes, marked }
}

/** ⧉ — copies `text` to the clipboard, with brief spoken/visible feedback. */
export function CopyButton({ text, label = t.ontologyCopy }: { text: string; label?: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle')

  useEffect(() => {
    if (status === 'idle') return
    const handle = setTimeout(() => setStatus('idle'), 1500)
    return () => clearTimeout(handle)
  }, [status])

  const copy = () => {
    if (!navigator.clipboard) {
      setStatus('failed')
      return
    }
    navigator.clipboard.writeText(text).then(
      () => setStatus('copied'),
      () => setStatus('failed'),
    )
  }

  return (
    <span className="od-copy-wrap">
      <button type="button" className="od-copy" onClick={copy} aria-label={label} title={label}>
        {status === 'copied' ? '✓' : '⧉'}
      </button>
      <span className="od-copy-status" role="status">
        {status === 'copied' ? t.ontologyCopied : status === 'failed' ? t.ontologyCopyFailed : ''}
      </span>
    </span>
  )
}

/** The «ακριβής μορφή στο γράφο» disclosure — renders nothing when not needed. */
export function ExactForm({ display, literals }: { display: string; literals: string[] }) {
  if (!exactFormNeeded(display, literals)) return null
  const differs = literals.some(l => l !== tidy(l)) || (literals.length === 1 && literals[0] !== display)
  const drawn = literals.map(visibleWhitespace)
  return (
    <details className="od-exact">
      <summary>
        {differs && literals.length === 1
          ? t.ontologyExactFormDiffers
          : t.ontologyExactFormSpellings(literals.length)}
      </summary>
      <ul className="od-exact-list">
        {literals.map((l, i) => (
          <li key={l} className="od-exact-item">
            <code className="od-exact-literal">{drawn[i].nodes}</code>
            <CopyButton text={l} />
          </li>
        ))}
      </ul>
      {literals.length > 1 && (
        <div className="od-exact-all">
          <CopyButton text={literals.join('\n')} label={t.ontologyCopyAll} />
          <span>{t.ontologyCopyAll}</span>
        </div>
      )}
      {drawn.some(d => d.marked) && <p className="od-exact-legend">{t.ontologyWhitespaceLegend}</p>}
    </details>
  )
}

/** Default row for course/book/university results: readable title, ⧉, exact form. */
export function ResultLine({ r }: { r: EntitySearchResult }) {
  const literals = r.literals ?? []
  return (
    <span className="od-list-item-detail">
      <span className="od-result-line">
        <span className="od-list-item-name">{r.title}</span>
        <CopyButton text={primaryLiteral(r)} />
      </span>
      <ExactForm display={r.title} literals={literals} />
    </span>
  )
}
