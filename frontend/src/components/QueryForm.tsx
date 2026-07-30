import { useState, useEffect, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { t } from '../i18n/el'
import type { Provider } from '../types'
import { CustomSelect } from './CustomSelect'

type Props = {
  providers: Provider[]
  disabled: boolean
  onSubmit: (question: string, provider: string, model: string) => void
  /** Pre-fills the input. Used by example chips and history clicks. */
  prefillQuestion?: string
  /** Show the clear button whenever results or a cached view are present. */
  showClear?: boolean
  onClear?: () => void
  /** Build SHA displayed in the header area next to provider selects.
   *  Currently unused — the badge that read it is commented out in App.tsx
   *  (search for `gitSha={GIT_SHA}`). Still accepted here so re-enabling
   *  that badge is a one-line change; underscored to satisfy
   *  noUnusedParameters in the meantime. */
  gitSha?: string
}

/**
 * QueryForm — hero search bar for the Console design.
 *
 * The search input lives inside the `.hero` section with a magnifier icon and
 * a solid accent "Αναζήτηση →" button. The provider/model selects and the
 * optional clear button sit below the input row as secondary controls.
 *
 * The textarea auto-grows vertically as the user types so the full question
 * stays visible. Enter submits; Shift+Enter inserts a newline.
 */
export function QueryForm({ providers, disabled, onSubmit, prefillQuestion, showClear, onClear, gitSha: _gitSha }: Props) {
  const [question, setQuestion] = useState('')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModel, setSelectedModel] = useState('')

  /** Ref used to auto-grow the textarea to fit its content. */
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (prefillQuestion !== undefined) setQuestion(prefillQuestion)
  }, [prefillQuestion])

  /** Resize the textarea to its content height after every question change
   *  (covers both typing and programmatic prefill). */
  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'          // shrink to content first
    el.style.height = el.scrollHeight + 'px'  // then grow to fit
  }, [question])

  const currentProvider = providers.find(p => p.id === (selectedProvider || providers[0]?.id))
  const models = currentProvider?.models ?? []

  const handleProviderChange = (id: string) => {
    setSelectedProvider(id)
    const p = providers.find(pr => pr.id === id)
    setSelectedModel(p?.models[0] ?? '')
  }

  /** Core submit logic shared by the form's onSubmit and the Enter key handler. */
  const doSubmit = () => {
    if (!question.trim() || providers.length === 0) return
    const provider = selectedProvider || providers[0].id
    const model = selectedModel || models[0] || ''
    onSubmit(question.trim(), provider, model)
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    doSubmit()
  }

  /** Enter submits; Shift+Enter inserts a newline so the textarea can grow. */
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSubmit()
    }
  }

  return (
    <form className="query-form" onSubmit={handleSubmit}>
      {/* ── Search bar ── */}
      <div className="query-input-wrap">
        <span className="query-input-prefix" aria-hidden="true">⌕</span>
        <textarea
          ref={textareaRef}
          className="query-input"
          rows={1}
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t.searchPlaceholder}
          disabled={disabled}
          aria-label={t.heroTitle}
        />
        <button
          type="submit"
          className="query-button"
          disabled={disabled || !question.trim()}
        >
          {disabled ? t.searching : t.searchButton}
        </button>
      </div>

      {/* ── Secondary controls: provider · model · build sha · clear ── */}
      <div className="query-controls">
        <div className="query-select-group">
          <span className="query-select-label">{t.providerLabel}</span>
          <CustomSelect
            value={selectedProvider || providers[0]?.id || ''}
            onChange={handleProviderChange}
            options={providers.map(p => ({ value: p.id, label: p.id }))}
            disabled={disabled || providers.length === 0}
            aria-label={t.providerLabel}
          />
        </div>

        <div className="query-select-group">
          <span className="query-select-label">{t.modelLabel}</span>
          <CustomSelect
            value={selectedModel || models[0] || ''}
            onChange={setSelectedModel}
            options={models.map(m => ({ value: m, label: m }))}
            disabled={disabled || models.length === 0}
            aria-label={t.modelLabel}
          />
        </div>

        {/* {gitSha && (
          <span className="query-select-label" style={{ color: 'var(--ink-faint)' }}>
            build {gitSha}
          </span>
        )} */}

        {showClear && (
          <button
            type="button"
            className="query-clear"
            onClick={onClear}
            disabled={disabled}
            aria-label="Εκκαθάριση αποτελεσμάτων"
          >
            ✕ εκκαθάριση
          </button>
        )}
      </div>
    </form>
  )
}
