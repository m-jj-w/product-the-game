// Mirrors server/app.py's Pydantic response models field-for-field.
// Keep in sync by hand -- there's no schema codegen here, this app is
// small enough that a drift would show up immediately in the browser.

export type Dim = 'D' | 'V' | 'F'
export type DimCounts = Record<Dim, number>

export interface PlayerView {
  id: string
  role_id: string
  skill_id: string | null
  skill_name: string | null
  skill_effect_summary: string | null
}

export interface PortfolioItem {
  card_id: string
  name: string
  quadrant: string
  offset: number
  tokens: DimCounts
  buffs: DimCounts
  required: DimCounts
}

export interface ActionOption {
  index: number
  description: string
}

export interface OutcomeView {
  result: 'win' | 'loss'
  reason: string
}

export interface HistoryEntryView {
  turn: number
  text: string
  at: string
}

export interface GameView {
  game_id: string
  seed: number
  turn: number
  bank: number
  players: PlayerView[]
  portfolio: PortfolioItem[]
  observation: string
  decision_kind: string | null
  decision_owner: string | null
  options: ActionOption[]
  outcome: OutcomeView | null
  history: HistoryEntryView[]
}

export type SpaceType = 'D' | 'V' | 'F' | 'skills' | 'chance'

export interface QuadrantView {
  id: string
  name: string
  order: number
  spaces: SpaceType[]
  milestone_name: string
  milestone_requirement: DimCounts
}

export interface BoardView {
  quadrants: QuadrantView[]
}

export interface ConceptView {
  id: string
  name: string
  tam: number
  medium: string[]
  categories: string[]
  flavor: string | null
}

export interface ConceptsView {
  concepts: ConceptView[]
}

export interface RulesView {
  text: string
}

export interface ApiErrorBody {
  detail?: string
}
