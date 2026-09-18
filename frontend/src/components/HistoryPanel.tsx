import type { GameView } from '../types'

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function HistoryPanel({ game }: { game: GameView }) {
  return (
    <section className="panel history-panel">
      <h2>History</h2>
      {game.history.length === 0 ? (
        <p className="empty-note">Nothing has happened yet.</p>
      ) : (
        <ul className="history-list">
          {game.history.map((h, i) => (
            <li key={`${h.turn}-${i}`} className="history-entry">
              <span className="history-time">{formatTime(h.at)}</span>
              <span className="history-turn">T{h.turn}</span>
              <span className="history-text">{h.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
