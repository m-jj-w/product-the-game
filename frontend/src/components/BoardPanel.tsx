import type { BoardView, GameView } from '../types'
import HexQuadrant from './HexQuadrant'

interface BoardPanelProps {
  board: BoardView | null
  game: GameView
  selectedConceptId: string | null
}

const LEGEND: Array<[string, string]> = [
  ['gateway', 'Gateway'],
  ['D', 'Desirability'],
  ['V', 'Viability'],
  ['F', 'Feasibility'],
  ['skills', 'Skill'],
  ['chance', 'Chance'],
]

export default function BoardPanel({ board, game, selectedConceptId }: BoardPanelProps) {
  if (!board) return null
  const quadrants = [...board.quadrants].sort((a, b) => a.order - b.order)

  return (
    <section className="panel board-panel">
      <h2>Board</h2>
      <div className="board-legend">
        {LEGEND.map(([key, label]) => (
          <span key={key} className="legend-item">
            <i className={`legend-swatch swatch-${key}`} />
            {label}
          </span>
        ))}
      </div>
      <div className="quadrant-grid">
        {quadrants.map((q) => (
          <HexQuadrant
            key={q.id}
            quadrant={q}
            occupants={game.portfolio.filter((p) => p.quadrant === q.id)}
            selectedConceptId={selectedConceptId}
          />
        ))}
      </div>
    </section>
  )
}
