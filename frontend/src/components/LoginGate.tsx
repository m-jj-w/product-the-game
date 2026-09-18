import { useState } from 'react'
import { verifyCredentials } from '../api'

// Must match deploy.sh's AUTH_USERNAME -- there's only one shared
// passphrase, so there's nothing useful to ask the player for here.
const USERNAME = 'play'

interface LoginGateProps {
  onSuccess: () => void
}

export default function LoginGate({ onSuccess }: LoginGateProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (await verifyCredentials(USERNAME, password)) {
        onSuccess()
      } else {
        setError('Incorrect passphrase.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="new-game-form" onSubmit={handleSubmit}>
      <h2>Enter the passphrase</h2>
      <label>
        Passphrase
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          autoFocus
        />
      </label>
      {error && <p className="error-banner">{error}</p>}
      <button type="submit" className="btn-primary" disabled={busy || !password}>
        {busy ? 'Checking…' : 'Enter'}
      </button>
    </form>
  )
}
