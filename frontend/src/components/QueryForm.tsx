import { useState, useEffect, type FormEvent } from 'react'
import { t } from '../i18n/el'
import type { Provider } from '../types'
import { CustomSelect } from './CustomSelect'

type Props = {
  providers: Provider[]
  disabled: boolean
  onSubmit: (question: string, provider: string, model: string) => void
  /** When set, pre-fills the input. Used by example-query and history clicks. */
  prefillQuestion?: string
  /** Show the clear button (true whenever there are results or a cached view). */
  showClear?: boolean
  onClear?: () => void
}

/**
 * QueryForm — the main input panel.
 *
 * Sharp-bordered text input with a decorative `›` prompt prefix, label-prefixed
 * provider/model selects, and a solid burnt-orange submit button.
 */
export function QueryForm({ providers, disabled, onSubmit, prefillQuestion, showClear, onClear }: Props) {
  const [question, setQuestion] = useState('')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModel, setSelectedModel] = useState('')

  // Sync the input when an example query is clicked from the empty state.
  useEffect(() => {
    if (prefillQuestion !== undefined) setQuestion(prefillQuestion)
  }, [prefillQuestion])

  const currentProvider = providers.find(p => p.id === (selectedProvider || providers[0]?.id))
  const models = currentProvider?.models ?? []

  const handleProviderChange = (id: string) => {
    setSelectedProvider(id)
    const p = providers.find(pr => pr.id === id)
    setSelectedModel(p?.models[0] ?? '')
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!question.trim() || providers.length === 0) return
    const provider = selectedProvider || providers[0].id
    const model = selectedModel || models[0] || ''
    onSubmit(question.trim(), provider, model)
  }

  return (
    <form className="query-form" onSubmit={handleSubmit}>
      <div className="query-input-wrap">
        <span className="query-input-prefix" aria-hidden="true">›</span>
        <input
          className="query-input"
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder={t.searchPlaceholder}
          disabled={disabled}
        />
      </div>

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

        <button
          type="submit"
          className="query-button"
          disabled={disabled || !question.trim()}
        >
          {disabled ? t.searching : t.searchButton}
        </button>
      </div>
    </form>
  )
}
