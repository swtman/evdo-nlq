/**
 * CustomSelect — a fully styled dropdown that replaces the native <select>.
 *
 * Native <select> open-popup styling is controlled by the OS on Windows and
 * cannot be themed via CSS. This component renders its own list so every
 * visual detail matches the parchment-brutalist design system.
 *
 * Keyboard support: Enter/Space to open, Arrow up/down to move, Escape to close.
 * Accessibility: role="combobox" + role="listbox" + aria-selected on options.
 */
import { useState, useRef, useEffect } from 'react'

type Option = { value: string; label: string }

type Props = {
  value: string
  onChange: (value: string) => void
  options: Option[]
  disabled?: boolean
  'aria-label'?: string
}

export function CustomSelect({ value, onChange, options, disabled, 'aria-label': ariaLabel }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const selectedLabel = options.find(o => o.value === value)?.label ?? value

  // Close when clicking outside the component
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(o => !o) }
    if (e.key === 'Escape') setOpen(false)
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const idx = options.findIndex(o => o.value === value)
      if (idx < options.length - 1) onChange(options[idx + 1].value)
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      const idx = options.findIndex(o => o.value === value)
      if (idx > 0) onChange(options[idx - 1].value)
    }
  }

  return (
    <div
      ref={ref}
      className={`custom-select${open ? ' open' : ''}${disabled ? ' disabled' : ''}`}
      role="combobox"
      aria-expanded={open}
      aria-haspopup="listbox"
      aria-label={ariaLabel}
      tabIndex={disabled ? -1 : 0}
      onKeyDown={handleKeyDown}
      onClick={() => { if (!disabled) setOpen(o => !o) }}
    >
      <span className="custom-select-value">{selectedLabel}</span>
      <span className="custom-select-arrow" aria-hidden="true">▾</span>

      {open && (
        <ul className="custom-select-list" role="listbox" aria-label={ariaLabel}>
          {options.map(opt => (
            <li
              key={opt.value}
              className={`custom-select-option${opt.value === value ? ' selected' : ''}`}
              role="option"
              aria-selected={opt.value === value}
              // mousedown fires before blur so we preventDefault to keep focus on the combobox
              onMouseDown={e => { e.preventDefault(); onChange(opt.value); setOpen(false) }}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
