import { useState, type FormEvent } from 'react'
import { t } from '../i18n/el'
import type { Provider } from '../types'

type Props = {
  providers: Provider[]
  disabled: boolean
  onSubmit: (question: string, provider: string, model: string) => void
}

/**
 * QueryForm — the main input panel.
 *
 * Renders a text input for the natural-language question, two selects for
 * provider and model, and a submit button.  All UI copy is sourced from the
 * `t` translation object so Greek strings are never hardcoded here.
 *
 * State is local: question text, selected provider id, and selected model id.
 * When the provider changes, the model resets to that provider's first model so
 * the selection is always valid.
 */
export function QueryForm({ providers, disabled, onSubmit }: Props) {
  const [question, setQuestion] = useState('')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedModel, setSelectedModel] = useState('')

  /** Resolve the currently active provider object for the model list. */
  const currentProvider = providers.find(p => p.id === (selectedProvider || providers[0]?.id))
  const models = currentProvider?.models ?? []

  /** Reset the model selection whenever the provider changes. */
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
    <form className="panel query-form" onSubmit={handleSubmit}>
      <input
        className="query-input"
        type="text"
        value={question}
        onChange={e => setQuestion(e.target.value)}
        placeholder={t.searchPlaceholder}
        disabled={disabled}
        autoFocus
      />
      <div className="query-controls">
        <select
          className="query-select"
          value={selectedProvider || providers[0]?.id || ''}
          onChange={e => handleProviderChange(e.target.value)}
          disabled={disabled || providers.length === 0}
          aria-label={t.providerLabel}
        >
          {providers.map(p => (
            <option key={p.id} value={p.id}>{p.id}</option>
          ))}
        </select>
        <select
          className="query-select"
          value={selectedModel || models[0] || ''}
          onChange={e => setSelectedModel(e.target.value)}
          disabled={disabled || models.length === 0}
          aria-label={t.modelLabel}
        >
          {models.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
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
