import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { AuthRequiredError, chooseAction, createGame, getBoard, getConcepts, getGame, onAuthRequired } from './api'
import BoardPanel from './components/BoardPanel'
import DecisionPanel from './components/DecisionPanel'
import Header from './components/Header'
import HistoryPanel from './components/HistoryPanel'
import LoginGate from './components/LoginGate'
import NewGameForm from './components/NewGameForm'
import PortfolioPanel from './components/PortfolioPanel'
import RulesModal from './components/RulesModal'
import TeamPanel from './components/TeamPanel'
import type { BoardView, ConceptView, GameView } from './types'

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

function App() {
  const [board, setBoard] = useState<BoardView | null>(null)
  const [concepts, setConcepts] = useState<ConceptView[]>([])
  const [game, setGame] = useState<GameView | null>(null)
  const [resumingGame, setResumingGame] = useState(
    () => new URLSearchParams(window.location.search).has('game'),
  )
  const [authRequired, setAuthRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null)
  const [rulesOpen, setRulesOpen] = useState(false)

  async function loadInitialData() {
    try {
      setBoard(await getBoard())
    } catch (e) {
      if (!(e instanceof AuthRequiredError)) setError(errorMessage(e))
    }
    try {
      setConcepts((await getConcepts()).concepts)
    } catch (e) {
      if (!(e instanceof AuthRequiredError)) setError(errorMessage(e))
    }

    // The game id lives in the URL (not localStorage) so a page refresh
    // resumes the same game via the server-persisted history, and the URL
    // stays shareable/bookmarkable.
    const resumeId = new URLSearchParams(window.location.search).get('game')
    if (!resumeId) {
      setResumingGame(false)
      return
    }
    setResumingGame(true)
    try {
      setGame(await getGame(resumeId))
    } catch (e) {
      if (!(e instanceof AuthRequiredError)) {
        setError(errorMessage(e))
        window.history.replaceState({}, '', window.location.pathname)
      }
    } finally {
      setResumingGame(false)
    }
  }

  useEffect(() => {
    onAuthRequired(() => setAuthRequired(true))
    void loadInitialData()
  }, [])

  const conceptsById = useMemo(() => Object.fromEntries(concepts.map((c) => [c.id, c])), [concepts])

  async function handleNewGame(playerIds: string[], seed?: number) {
    setBusy(true)
    setError(null)
    try {
      const view = await createGame(playerIds, seed)
      setGame(view)
      setSelectedConceptId(null)
      window.history.pushState({}, '', `?game=${view.game_id}`)
    } catch (e) {
      if (!(e instanceof AuthRequiredError)) setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleChoose(actionIndex: number) {
    if (!game) return
    setBusy(true)
    setError(null)
    try {
      setGame(await chooseAction(game.game_id, actionIndex))
    } catch (e) {
      if (!(e instanceof AuthRequiredError)) setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <Header game={game} onOpenRules={() => setRulesOpen(true)} />
      {error && <div className="error-banner">{error}</div>}
      {authRequired ? (
        <LoginGate
          onSuccess={() => {
            setAuthRequired(false)
            setError(null)
            loadInitialData()
          }}
        />
      ) : resumingGame ? (
        <p className="empty-note">Loading…</p>
      ) : !game ? (
        <NewGameForm onSubmit={handleNewGame} busy={busy} />
      ) : (
        <div className="layout">
          <div className="col-main">
            <BoardPanel board={board} game={game} selectedConceptId={selectedConceptId} />
            <PortfolioPanel
              game={game}
              board={board}
              concepts={conceptsById}
              selectedConceptId={selectedConceptId}
              onSelect={setSelectedConceptId}
            />
            <DecisionPanel
              key={`${game.game_id}:${game.history.length}`}
              game={game}
              busy={busy}
              onChoose={handleChoose}
            />
          </div>
          <div className="col-side">
            <TeamPanel game={game} />
            <HistoryPanel game={game} />
          </div>
        </div>
      )}
      {rulesOpen && <RulesModal onClose={() => setRulesOpen(false)} />}
    </div>
  )
}

export default App
