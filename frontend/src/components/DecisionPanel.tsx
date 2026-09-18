import { useState } from 'react'
import type { GameView } from '../types'

interface DecisionPanelProps {
  game: GameView
  busy: boolean
  onChoose: (actionIndex: number) => void
}

const KIND_TITLES: Record<string, string> = {
  move: 'Move a Concept',
  cross_milestone: 'Cross the Milestone?',
  skill: 'You drew a Skill',
  chance_removal: 'Chance: choose a Concept to remove',
  research_breakthrough: 'Research Breakthrough',
  close: 'Close phase',
}

export default function DecisionPanel({ game, busy, onChoose }: DecisionPanelProps) {
  const [selected, setSelected] = useState<number | null>(null)

  if (game.outcome) {
    return (
      <section className={`panel decision-panel outcome-panel ${game.outcome.result}`}>
        <h2>{game.outcome.result === 'win' ? 'You won!' : 'Game over'}</h2>
        <p>{game.outcome.reason}</p>
      </section>
    )
  }

  if (!game.decision_kind) {
    return null
  }

  const title = KIND_TITLES[game.decision_kind] ?? game.decision_kind

  return (
    <section className="panel decision-panel">
      <h2>{title}</h2>
      <p className="decision-owner">Decision owner: {game.decision_owner}</p>
      <div className="decision-options">
        {game.options.map((opt) => (
          <label
            key={opt.index}
            className={selected === opt.index ? 'decision-option selected' : 'decision-option'}
          >
            <input
              type="radio"
              name="decision-option"
              checked={selected === opt.index}
              onChange={() => setSelected(opt.index)}
            />
            {opt.description}
          </label>
        ))}
      </div>
      <button
        type="button"
        className="btn-primary"
        disabled={selected === null || busy}
        onClick={() => selected !== null && onChoose(selected)}
      >
        {busy ? 'Applying…' : 'Confirm'}
      </button>
    </section>
  )
}
