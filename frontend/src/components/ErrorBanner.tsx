import { t } from '../i18n/el'

type Props = {
  message: string
  onDismiss: () => void
}

/**
 * ErrorBanner — dismissable error display, parchment-brutalist style.
 *
 * Renders a `// σφάλμα:` prefix above the message in a warm-tinted panel.
 * Uses `role="alert"` so screen readers announce the error automatically.
 */
export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="error-banner" role="alert">
      <div className="error-banner-head">
        <span className="error-prefix">{t.errorPrefix}</span>
        <button
          className="error-dismiss"
          onClick={onDismiss}
          type="button"
          aria-label={t.errorDismissLabel}
        >
          {t.errorDismiss}
        </button>
      </div>
      <p className="error-message">{message}</p>
    </div>
  )
}
