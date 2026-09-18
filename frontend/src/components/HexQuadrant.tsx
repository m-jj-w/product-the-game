import type { PortfolioItem, QuadrantView } from '../types'

const SPACE_COLORS: Record<string, string> = {
  gateway: 'var(--gateway-color)',
  D: 'var(--d-color)',
  V: 'var(--v-color)',
  F: 'var(--f-color)',
  skills: 'var(--skills-color)',
  chance: 'var(--chance-color)',
}

const SPACE_LABELS: Record<string, string> = {
  gateway: 'Gateway',
  D: 'Desirability',
  V: 'Viability',
  F: 'Feasibility',
  skills: 'Skill',
  chance: 'Chance',
}

// Gateway (offset 0) + 15 coded spaces, per CLAUDE.md.
const TOTAL_SPACES = 16

function hexPoints(cx: number, cy: number, r: number): string {
  const pts: string[] = []
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 180) * (60 * i)
    pts.push(`${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`)
  }
  return pts.join(' ')
}

function ringPoint(i: number, cx: number, cy: number, r: number): [number, number] {
  const angle = (i / TOTAL_SPACES) * 2 * Math.PI - Math.PI / 2
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)]
}

interface HexQuadrantProps {
  quadrant: QuadrantView
  occupants: PortfolioItem[]
  selectedConceptId: string | null
}

export default function HexQuadrant({ quadrant, occupants, selectedConceptId }: HexQuadrantProps) {
  const size = 220
  const cx = size / 2
  const cy = size / 2
  const ringR = 82
  const hexR = 16

  const byOffset = new Map<number, PortfolioItem[]>()
  for (const item of occupants) {
    const list = byOffset.get(item.offset) ?? []
    list.push(item)
    byOffset.set(item.offset, list)
  }

  return (
    <div className="hex-quadrant">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${quadrant.name} board`}>
        {Array.from({ length: TOTAL_SPACES }, (_, i) => {
          const [x, y] = ringPoint(i, cx, cy, ringR)
          const type = i === 0 ? 'gateway' : quadrant.spaces[i - 1]
          const r = i === 0 ? hexR * 1.15 : hexR
          return (
            <polygon
              key={i}
              points={hexPoints(x, y, r)}
              fill={SPACE_COLORS[type] ?? '#999'}
              fillOpacity={i === 0 ? 0.9 : 0.55}
              stroke="var(--panel-bg)"
              strokeWidth={1.5}
            >
              <title>{i === 0 ? 'Gateway' : `Space ${i}: ${SPACE_LABELS[type]}`}</title>
            </polygon>
          )
        })}
        {Array.from(byOffset.entries()).flatMap(([offset, items]) => {
          const [x, y] = ringPoint(offset, cx, cy, ringR)
          return items.map((item, idx) => {
            const spread = items.length > 1 ? (idx - (items.length - 1) / 2) * 11 : 0
            const selected = item.card_id === selectedConceptId
            return (
              <circle
                key={item.card_id}
                className={selected ? 'concept-marker selected' : 'concept-marker'}
                cx={x + spread}
                cy={y - 14}
                r={selected ? 8 : 6.5}
                fill="var(--accent)"
                stroke="var(--panel-bg)"
                strokeWidth={1.5}
              >
                <title>{item.name}</title>
              </circle>
            )
          })
        })}
      </svg>
      <div className="hex-quadrant-label">
        <strong>{quadrant.name}</strong>
        <span className="milestone-req">
          Milestone: D{quadrant.milestone_requirement.D} V{quadrant.milestone_requirement.V} F
          {quadrant.milestone_requirement.F}
        </span>
      </div>
    </div>
  )
}
