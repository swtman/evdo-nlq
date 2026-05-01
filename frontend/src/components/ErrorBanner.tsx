import { t } from '../i18n/el'

type Props = {
  /** Human-readable error message forwarded from the backend SSE `error` event. */
  message: string
  /** Callback to transition the query state machine back to `idle`. */
  onDismiss: () => void
}

/**
 * ErrorBanner — a dismissible error alert shown when the SSE stream reports
 * an `error` event.
 *
 * Uses `role="alert"` so screen readers announce the error automatically.
 * The dismiss button calls `onDismiss` which triggers `DISMISS_ERROR` in the
 * reducer and returns the UI to the idle state so the user can retry.
 */
export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="panel panel--red error-banner" role="alert">
      <span><strong>{t.errorPrefix}</strong> {message}</span>
      <button
        className="dismiss-btn"
        onClick={onDismiss}
        aria-label={t.errorDismiss}
        type="button"
      >
        {t.errorDismiss}
      </button>
    </div>
  )
}
