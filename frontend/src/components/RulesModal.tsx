import { useEffect, useState } from 'react'
import { AuthRequiredError, getRules } from '../api'

export default function RulesModal({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRules()
      .then((r) => setText(r.text))
      .catch((e) => {
        // AuthRequiredError already triggers the app-level LoginGate
        // (App.tsx's onAuthRequired handler) -- nothing more to show here.
        if (!(e instanceof AuthRequiredError)) {
          setError(e instanceof Error ? e.message : String(e))
        }
      })
  }, [])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal rules-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Rules</h2>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">
          {error && <p className="error-banner">{error}</p>}
          {!error && text === null && <p>Loading…</p>}
          {text !== null && <pre className="rules-text">{text}</pre>}
        </div>
      </div>
    </div>
  )
}
