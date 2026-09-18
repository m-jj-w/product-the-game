import type { GameView } from '../types'

interface HeaderProps {
  game: GameView | null
  onOpenRules: () => void
}

const TAM_GOAL = 1.0

export default function Header({ game, onOpenRules }: HeaderProps) {
  const bank = game?.bank ?? 0
  const pct = Math.min(100, (bank / TAM_GOAL) * 100)

  return (
    <header className="app-header">
      <h1>Product: The Game</h1>
      {game && (
        <div className="bank-progress" title={`$${bank.toFixed(2)}B of $${TAM_GOAL.toFixed(0)}B banked`}>
          <div className="bank-progress-track">
            <div className="bank-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="bank-progress-label">
            ${bank.toFixed(2)}B / ${TAM_GOAL.toFixed(0)}B banked
          </span>
        </div>
      )}
      <div className="header-right">
        {game && <span className="turn-counter">Turn {game.turn} / 50</span>}
        <button type="button" className="btn-secondary" onClick={onOpenRules}>
          Rules
        </button>
      </div>
    </header>
  )
}
