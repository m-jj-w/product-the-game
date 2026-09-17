"""Lightweight hot-seat web server for Product: The Game.

One browser tab, players pass it around and discuss out loud -- matches
rules.md sec 3 ("the players discuss and the PM makes the final call").
No player identity, no sessions, no websockets: nothing needs to push an
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
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.llm_agent import describe_action
from engine.engine import (
    NewGameConfig,
    apply,
    current_decision,
    is_over,
    legal_actions,
    new_game,
    observe,
)
from engine.schema import GameData, load_game_data
from engine.state import GameState
from server.auth import BasicAuthMiddleware
from server.store import FirestoreGameStore, GameRecord, GameStore, InMemoryGameStore, replay

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="Product: The Game")
app.add_middleware(BasicAuthMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


class PortfolioItem(BaseModel):
    card_id: str
    name: str
    quadrant: str
    offset: int
    tokens: dict[str, int]


class ActionOption(BaseModel):
    index: int
    description: str


class OutcomeView(BaseModel):
    result: str
    reason: str


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


def _build_view(game_id: str, state: GameState, seed: int) -> GameView:
    decision = current_decision(state)
    outcome = is_over(state)

    players = [
        PlayerView(
            id=p.id,
            role_id=p.role_id,
            skill_id=p.skill_id,
            skill_name=state.data.skills[p.skill_id].name if p.skill_id else None,
        )
        for p in state.players
    ]
    portfolio = [
        PortfolioItem(
            card_id=c.card_id,
            name=state.data.concepts[c.card_id].name,
            quadrant=c.position.quadrant_id,
            offset=c.position.offset,
            tokens={"D": c.tokens.D, "V": c.tokens.V, "F": c.tokens.F},
        )
        for c in state.portfolio
    ]
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
    )


def _load_record(store: GameStore, game_id: str) -> GameRecord:
    record = store.load(game_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no game '{game_id}'")
    return record


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/games", response_model=GameView)
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
    return _build_view(game_id, state, seed)


@app.get("/games/{game_id}", response_model=GameView)
def get_game(
    game_id: str,
    data: GameData = Depends(get_game_data),
    store: GameStore = Depends(get_game_store),
) -> GameView:
    record = _load_record(store, game_id)
    state = replay(data, record)
    return _build_view(game_id, state, record.seed)


@app.post("/games/{game_id}/actions", response_model=GameView)
def choose_action(
    game_id: str,
    req: ChooseActionRequest,
    data: GameData = Depends(get_game_data),
    store: GameStore = Depends(get_game_store),
) -> GameView:
    record = _load_record(store, game_id)
    state = replay(data, record)
    if is_over(state) is not None:
        raise HTTPException(status_code=400, detail="game is already over")

    actions = legal_actions(state)
    if not (0 <= req.action_index < len(actions)):
        raise HTTPException(
            status_code=400,
            detail=f"action_index must be between 0 and {len(actions) - 1}",
        )

    new_state = apply(state, actions[req.action_index])
    new_record = GameRecord(
        player_ids=record.player_ids,
        seed=record.seed,
        action_indices=[*record.action_indices, req.action_index],
    )
    store.save(game_id, new_record)
    return _build_view(game_id, new_state, record.seed)
