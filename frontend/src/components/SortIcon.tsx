import type { SortDirection } from '../types'

type Props = { direction: SortDirection }

/**
 * SortIcon — inline SVG for the three sort states.
 *
 * Mirrors the icons in `public/dafaultIndicator.png` (idle), `public/indicator1.png`
 * (asc), and `public/indicator2.png` (desc) as vector so they respect CSS color
 * variables and work in both light and dark themes.
 */
export function SortIcon({ direction }: Props) {
  if (direction === 'idle') {
    return (
      <svg className="sort-icon" viewBox="0 0 13 13" fill="none" aria-hidden="true">
        <path d="M4 5 L6.5 2.5 L9 5" stroke="var(--ink-faint)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M4 8 L6.5 10.5 L9 8" stroke="var(--ink-faint)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    )
  }
  if (direction === 'asc') {
    return (
      <svg className="sort-icon" viewBox="0 0 13 13" fill="none" aria-hidden="true">
        <path d="M4.5 9.5 L4.5 3 M3 7.5 L4.5 9.5 L6 7.5" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <text x="7.5" y="6.5" fontFamily="var(--font-mono)" fontSize="4.5" fontWeight="700" fill="var(--accent)">A</text>
        <text x="7.5" y="11.5" fontFamily="var(--font-mono)" fontSize="4.5" fontWeight="700" fill="var(--accent)">Z</text>
      </svg>
    )
  }
  // desc
  return (
    <svg className="sort-icon" viewBox="0 0 13 13" fill="none" aria-hidden="true">
      <path d="M4.5 3.5 L4.5 10 M3 7 L4.5 9 L6 7" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <text x="7.5" y="6.5" fontFamily="var(--font-mono)" fontSize="4.5" fontWeight="700" fill="var(--accent)">Z</text>
      <text x="7.5" y="11.5" fontFamily="var(--font-mono)" fontSize="4.5" fontWeight="700" fill="var(--accent)">A</text>
    </svg>
  )
}
