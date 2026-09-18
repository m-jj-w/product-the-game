import { useState } from 'react'

interface NewGameFormProps {
  onSubmit: (playerIds: string[], seed?: number) => void
  busy: boolean
}

export default function NewGameForm({ onSubmit, busy }: NewGameFormProps) {
  const [players, setPlayers] = useState('alice,bob,carol')
  const [seed, setSeed] = useState('')

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const ids = players
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    if (ids.length === 0) return
    const seedNum = seed.trim() === '' ? undefined : Number(seed)
    onSubmit(ids, seedNum)
  }

  return (
    <form className="new-game-form" onSubmit={handleSubmit}>
      <h2>Start a new game</h2>
      <label>
        Player ids (comma-separated, 1-5 players)
        <input
          value={players}
          onChange={(e) => setPlayers(e.target.value)}
          placeholder="alice,bob,carol"
          required
        />
      </label>
      <label>
        Seed (optional)
        <input
          value={seed}
          onChange={(e) => setSeed(e.target.value)}
          type="number"
          placeholder="random"
        />
      </label>
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy ? 'Starting…' : 'New Game'}
      </button>
    </form>
  )
}
