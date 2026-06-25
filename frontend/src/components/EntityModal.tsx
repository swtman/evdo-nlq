/**
 * EntityModal — centered dialog for browsing a searchable entity list.
 *
 * Closes on: Esc key, backdrop click, ✕ button.
 * Focuses the first focusable child (search input) on mount.
 * Locks page scroll while open; respects prefers-reduced-motion via CSS.
 */

import { useEffect, useRef, type ReactNode } from 'react'
import { t } from '../i18n/el'

interface EntityModalProps {
  title: string
  /** Live result count shown in the header chip. Omit to hide the chip. */
  count?: number
  onClose: () => void
  children: ReactNode
}

export function EntityModal({ title, count, onClose, children }: EntityModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)

  // Close on Esc
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  // Lock background scroll while modal is open
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])

  // Auto-focus the first input or the close button on open
  useEffect(() => {
    const first = dialogRef.current?.querySelector<HTMLElement>('input[type="search"]')
      ?? dialogRef.current?.querySelector<HTMLElement>('button.od-modal-close')
    first?.focus()
  }, [])

  return (
    <div
      className="od-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="od-modal-title"
    >
      <div
        className="od-modal"
        ref={dialogRef}
        onClick={e => e.stopPropagation()}
      >
        <div className="od-modal-head">
          <span id="od-modal-title" className="od-modal-title">{title}</span>
          {count !== undefined && (
            <span className="od-modal-count">{t.ontologyModalResults(count)}</span>
          )}
          <button
            className="od-modal-close"
            type="button"
            aria-label={t.ontologyModalClose}
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <div className="od-modal-body">
          {children}
        </div>
      </div>
    </div>
  )
}
