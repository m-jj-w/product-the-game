import type { BoardView, ConceptView, GameView, PortfolioItem } from '../types'

interface PortfolioPanelProps {
  game: GameView
  board: BoardView | null
  concepts: Record<string, ConceptView>
  selectedConceptId: string | null
  onSelect: (id: string | null) => void
}

const DIMS = ['D', 'V', 'F'] as const

function shortfalls(item: PortfolioItem): string[] {
  return DIMS.filter((d) => item.tokens[d] + item.buffs[d] < item.required[d]).map(
    (d) => `Needs ${item.required[d] - (item.tokens[d] + item.buffs[d])} ${d}`,
  )
}

export default function PortfolioPanel({
  game,
  board,
  concepts,
  selectedConceptId,
  onSelect,
}: PortfolioPanelProps) {
  const quadrantById = Object.fromEntries((board?.quadrants ?? []).map((q) => [q.id, q]))

  return (
    <section className="panel portfolio-panel">
      <h2>Portfolio</h2>
      {game.portfolio.length === 0 && <p className="empty-note">No active Concepts.</p>}
      <div className="portfolio-grid">
        {game.portfolio.map((item) => {
          const concept = concepts[item.card_id]
          const quadrant = quadrantById[item.quadrant]
          const needs = shortfalls(item)
          const boosted = quadrant
            ? DIMS.some((d) => item.required[d] > quadrant.milestone_requirement[d])
            : false
          const selected = item.card_id === selectedConceptId

          return (
            <button
              type="button"
              key={item.card_id}
              className={selected ? 'concept-card selected' : 'concept-card'}
              onClick={() => onSelect(selected ? null : item.card_id)}
            >
              <div className="concept-card-header">
                <span className="concept-name">{item.name}</span>
                {concept && <span className="concept-tam">${concept.tam.toFixed(2)}B</span>}
              </div>
              {concept && (concept.medium.length > 0 || concept.categories.length > 0) && (
                <div className="concept-tags">
                  {[...concept.medium, ...concept.categories].map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <div className="concept-position">
                {quadrant ? quadrant.name : item.quadrant} · space {item.offset}
              </div>
              <div className="dvf-table">
                <div className="dvf-row dvf-header">
                  <span />
                  {DIMS.map((d) => (
                    <span key={d}>{d}</span>
                  ))}
                </div>
                <div className="dvf-row">
                  <span className="dvf-row-label">Tokens</span>
                  {DIMS.map((d) => (
                    <span key={d}>{item.tokens[d]}</span>
                  ))}
                </div>
                <div className="dvf-row">
                  <span className="dvf-row-label">Buffs</span>
                  {DIMS.map((d) => (
                    <span key={d}>{item.buffs[d] >= 0 ? `+${item.buffs[d]}` : item.buffs[d]}</span>
                  ))}
                </div>
                <div className="dvf-row">
                  <span className="dvf-row-label">Required</span>
                  {DIMS.map((d) => (
                    <span key={d}>{item.required[d]}</span>
                  ))}
                </div>
              </div>
              <div className="concept-badges">
                {needs.length === 0 ? (
                  <span className="badge badge-ok">Qualifies</span>
                ) : (
                  needs.map((n) => (
                    <span key={n} className="badge badge-warn">
                      {n}
                    </span>
                  ))
                )}
                {boosted && <span className="badge badge-info">Requirement raised</span>}
              </div>
              {concept?.flavor && <p className="concept-flavor">{concept.flavor}</p>}
            </button>
          )
        })}
      </div>
    </section>
  )
}
