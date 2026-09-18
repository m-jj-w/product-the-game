import type { ApiErrorBody, BoardView, ConceptsView, GameView, RulesView } from './types'

// Every call is relative ("/api/..."), so this works unmodified whether
// it's Vite's dev proxy (vite.config.ts) or Firebase Hosting's /api/**
// rewrite (firebase.json) putting the real backend behind it.

const AUTH_STORAGE_KEY = 'ptg_auth'

export class AuthRequiredError extends Error {}

let authRequiredHandler: (() => void) | null = null

// Firebase Hosting serves the static page directly, so the backend's
// shared-passphrase Basic Auth gate (server/auth.py) only ever shows up on
// /api/** calls -- the page itself always loads first. A fetch()-triggered
// 401 doesn't reliably raise the browser's native auth popup the way a
// top-level navigation would, so the app supplies credentials itself
// (LoginGate.tsx) instead of relying on that popup.
export function onAuthRequired(handler: () => void): void {
  authRequiredHandler = handler
}

function getStoredAuthHeader(): string | null {
  try {
    return sessionStorage.getItem(AUTH_STORAGE_KEY)
  } catch {
    return null
  }
}

function storeAuthHeader(value: string): void {
  try {
    sessionStorage.setItem(AUTH_STORAGE_KEY, value)
  } catch {
    // Private browsing or similar -- credentials just won't survive a
    // refresh, and the 401 flow below re-prompts next time.
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const authHeader = getStoredAuthHeader()
  if (authHeader) headers.set('Authorization', authHeader)

  const response = await fetch(path, { ...init, headers })
  if (response.status === 401) {
    authRequiredHandler?.()
    throw new AuthRequiredError('authentication required')
  }
  const body = (await response.json()) as T | ApiErrorBody
  if (!response.ok) {
    const detail = (body as ApiErrorBody).detail
    throw new Error(detail || `request failed (${response.status})`)
  }
  return body as T
}

export async function verifyCredentials(username: string, password: string): Promise<boolean> {
  const header = `Basic ${btoa(`${username}:${password}`)}`
  const response = await fetch('/api/board', { headers: { Authorization: header } })
  if (response.status === 401) return false
  if (!response.ok) throw new Error(`request failed (${response.status})`)
  storeAuthHeader(header)
  return true
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
