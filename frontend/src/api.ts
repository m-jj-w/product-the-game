import type { ApiErrorBody, BoardView, ConceptsView, GameView, RulesView } from './types'

// Every call is relative ("/api/..."), so this works unmodified whether
// it's Vite's dev proxy (vite.config.ts) or Firebase Hosting's /api/**
// rewrite (firebase.json) putting the real backend behind it.

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = (await response.json()) as T | ApiErrorBody
  if (!response.ok) {
    const detail = (body as ApiErrorBody).detail
    throw new Error(detail || `request failed (${response.status})`)
  }
  return body as T
}

export function getBoard(): Promise<BoardView> {
  return request<BoardView>('/api/board')
}

export function getConcepts(): Promise<ConceptsView> {
  return request<ConceptsView>('/api/concepts')
}

export function getRules(): Promise<RulesView> {
  return request<RulesView>('/api/rules')
}

export function createGame(playerIds: string[], seed?: number): Promise<GameView> {
  const body: { player_ids: string[]; seed?: number } = { player_ids: playerIds }
  if (seed !== undefined) body.seed = seed
  return request<GameView>('/api/games', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getGame(gameId: string): Promise<GameView> {
  return request<GameView>(`/api/games/${gameId}`)
}

export function chooseAction(gameId: string, actionIndex: number): Promise<GameView> {
  return request<GameView>(`/api/games/${gameId}/actions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action_index: actionIndex }),
  })
}
