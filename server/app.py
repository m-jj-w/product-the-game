"""Product: The Game's JSON API.

A pure API under /api/* -- Firebase Hosting serves the built React
frontend (frontend/dist) directly as static files, rewriting only
/api/** to this Cloud Run service (see firebase.json, deploy.sh). No
player identity, no sessions, no websockets: nothing needs to push an
update to an idle client, so plain request/response is enough.

Games persist through a GameStore (server/store.py) -- in-memory by
default (local dev, tests), Firestore in production (see deploy.sh,
which sets GOOGLE_CLOUD_PROJECT). A shared-passphrase gate
(server/auth.py) is similarly a no-op unless AUTH_PASSWORD is set.
"""

from __future__ import annotations

import os
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from agents.llm_agent import RULES_PATH, describe_action, describe_skill
from engine.engine import (
    NewGameConfig,
    apply,
    current_decision,
    is_over,
    legal_actions,
    new_game,
    observe,
)
from engine.modifiers import compute_skill_buffs, required_dvf
from engine.schema import GameData, load_game_data
from engine.state import GameState
from server.auth import BasicAuthMiddleware
from server.store import (
    FirestoreGameStore,
    GameRecord,
    GameStore,
    HistoryEntry,
    InMemoryGameStore,
    narrate_step,
    replay_with_history,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="Product: The Game")
app.add_middleware(BasicAuthMiddleware)

_STORE: GameStore = (
    FirestoreGameStore() if os.environ.get("GOOGLE_CLOUD_PROJECT") else InMemoryGameStore()
)


def get_game_data() -> GameData:
    """The loaded card/board data. Overridden in tests with the synthetic
    fixture; PRODUCT_GAME_DATA_DIR lets a local run point elsewhere too."""
    data_dir = Path(os.environ.get("PRODUCT_GAME_DATA_DIR", DEFAULT_DATA_DIR))
    return load_game_data(data_dir)


def get_game_store() -> GameStore:
    """Where games are persisted. A single store instance for the life of
    the process -- constructed once at import time based on
    GOOGLE_CLOUD_PROJECT (deploy.sh always sets it; local/dev/tests never
    do). Overridden in tests to a fresh InMemoryGameStore per test."""
    return _STORE


class NewGameRequest(BaseModel):
    player_ids: list[str]
    seed: int | None = None


class ChooseActionRequest(BaseModel):
    action_index: int


class PlayerView(BaseModel):
    id: str
    role_id: str
    skill_id: str | None
    skill_name: str | None
    skill_effect_summary: str | None


class PortfolioItem(BaseModel):
    card_id: str
    name: str
    quadrant: str
    offset: int
    tokens: dict[str, int]
    buffs: dict[str, int]
    required: dict[str, int]


class ActionOption(BaseModel):
    index: int
    description: str


class OutcomeView(BaseModel):
    result: str
    reason: str


class HistoryEntryView(BaseModel):
    turn: int
    text: str
    at: str


class GameView(BaseModel):
    game_id: str
    seed: int
    turn: int
    bank: float
    players: list[PlayerView]
    portfolio: list[PortfolioItem]
    observation: str
    decision_kind: str | None
    decision_owner: str | None
    options: list[ActionOption]
    outcome: OutcomeView | None
    history: list[HistoryEntryView]


class QuadrantView(BaseModel):
    id: str
    name: str
    order: int
    spaces: list[str]
    milestone_name: str
    milestone_requirement: dict[str, int]


class BoardView(BaseModel):
    quadrants: list[QuadrantView]


class ConceptView(BaseModel):
    id: str
    name: str
    tam: float
    medium: list[str]
    categories: list[str]
    flavor: str | None


class ConceptsView(BaseModel):
    concepts: list[ConceptView]


class RulesView(BaseModel):
    text: str


def _build_view(game_id: str, state: GameState, seed: int, history: list[HistoryEntry]) -> GameView:
    decision = current_decision(state)
    outcome = is_over(state)

    players = [
        PlayerView(
            id=p.id,
            role_id=p.role_id,
            skill_id=p.skill_id,
            skill_name=state.data.skills[p.skill_id].name if p.skill_id else None,
            skill_effect_summary=(
                describe_skill(state.data.skills[p.skill_id]) if p.skill_id else None
            ),
        )
        for p in state.players
    ]
    portfolio = []
    for c in state.portfolio:
        card = state.data.concepts[c.card_id]
        quadrant = state.data.board.quadrant(c.position.quadrant_id)
        buffs = compute_skill_buffs(state, card)
        required = required_dvf(card, quadrant)
        portfolio.append(
            PortfolioItem(
                card_id=c.card_id,
                name=card.name,
                quadrant=c.position.quadrant_id,
                offset=c.position.offset,
                tokens={"D": c.tokens.D, "V": c.tokens.V, "F": c.tokens.F},
                buffs={"D": buffs.D, "V": buffs.V, "F": buffs.F},
                required={"D": required.D, "V": required.V, "F": required.F},
            )
        )
    options = (
        [
            ActionOption(index=i, description=describe_action(a, state))
            for i, a in enumerate(decision.actions)
        ]
        if decision is not None
        else []
    )
    observed_by = decision.owner if decision is not None else state.active_player.id

    return GameView(
        game_id=game_id,
        seed=seed,
        turn=state.turn,
        bank=state.bank,
        players=players,
        portfolio=portfolio,
        observation=observe(state, observed_by),
        decision_kind=decision.kind if decision is not None else None,
        decision_owner=decision.owner if decision is not None else None,
        options=options,
        outcome=OutcomeView(result=outcome.result, reason=outcome.reason) if outcome else None,
        history=[HistoryEntryView(turn=h.turn, text=h.text, at=h.at) for h in reversed(history)],
    )


def _load_record(store: GameStore, game_id: str) -> GameRecord:
    record = store.load(game_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no game '{game_id}'")
    return record


@app.get("/api/board", response_model=BoardView)
def get_board(data: GameData = Depends(get_game_data)) -> BoardView:
    """The board layout -- static for the life of a game, fetched once by
    the client rather than repeated in every GameView."""
    quadrants = sorted(data.board.quadrants, key=lambda q: q.order)
    return BoardView(
        quadrants=[
            QuadrantView(
                id=q.id,
                name=q.name,
                order=q.order,
                spaces=list(q.spaces),
                milestone_name=q.milestone.name,
                milestone_requirement={
                    "D": q.milestone.requirement.D,
                    "V": q.milestone.requirement.V,
                    "F": q.milestone.requirement.F,
                },
            )
            for q in quadrants
        ]
    )


@app.get("/api/concepts", response_model=ConceptsView)
def get_concepts(data: GameData = Depends(get_game_data)) -> ConceptsView:
    """Every Concept's static definition -- fetched once, joined against
    PortfolioItem.card_id client-side (keeps GameView from repeating
    name/medium/categories/tam on every response)."""
    return ConceptsView(
        concepts=[
            ConceptView(
                id=c.id,
                name=c.name,
                tam=c.tam,
                medium=list(c.medium),
                categories=list(c.categories),
                flavor=c.flavor,
            )
            for c in data.concepts.values()
        ]
    )


@app.get("/api/rules", response_model=RulesView)
def get_rules() -> RulesView:
    return RulesView(text=RULES_PATH.read_text())


@app.post("/api/games", response_model=GameView)
def create_game(
    req: NewGameRequest,
    data: GameData = Depends(get_game_data),
    store: GameStore = Depends(get_game_store),
) -> GameView:
    seed = req.seed if req.seed is not None else random.randrange(2**32)
    try:
        state = new_game(NewGameConfig(data=data, player_ids=req.player_ids), seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    game_id = str(uuid.uuid4())
    record = GameRecord(player_ids=req.player_ids, seed=seed)
    store.save(game_id, record)
    return _build_view(game_id, state, seed, [])


@app.get("/api/games/{game_id}", response_model=GameView)
def get_game(
    game_id: str,
    data: GameData = Depends(get_game_data),
    store: GameStore = Depends(get_game_store),
) -> GameView:
    record = _load_record(store, game_id)
    state, history = replay_with_history(data, record)
    return _build_view(game_id, state, record.seed, history)


@app.post("/api/games/{game_id}/actions", response_model=GameView)
def choose_action(
    game_id: str,
    req: ChooseActionRequest,
    data: GameData = Depends(get_game_data),
    store: GameStore = Depends(get_game_store),
) -> GameView:
    record = _load_record(store, game_id)
    state, history = replay_with_history(data, record)
    if is_over(state) is not None:
        raise HTTPException(status_code=400, detail="game is already over")

    actions = legal_actions(state)
    if not (0 <= req.action_index < len(actions)):
        raise HTTPException(
            status_code=400,
            detail=f"action_index must be between 0 and {len(actions) - 1}",
        )

    chosen_action = actions[req.action_index]
    new_state = apply(state, chosen_action)
    timestamp = datetime.now(UTC).isoformat()
    new_record = GameRecord(
        player_ids=record.player_ids,
        seed=record.seed,
        action_indices=[*record.action_indices, req.action_index],
        action_timestamps=[*record.action_timestamps, timestamp],
    )
    store.save(game_id, new_record)

    new_history = [
        *history,
        HistoryEntry(
            turn=new_state.turn, text=narrate_step(state, new_state, chosen_action), at=timestamp
        ),
    ]
    return _build_view(game_id, new_state, record.seed, new_history)
