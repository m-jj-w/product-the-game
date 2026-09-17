"""Where games live between requests.

Stores the seed plus the sequence of chosen action indices, not a
serialized GameState -- CLAUDE.md's own invariant ("a seed plus a list
of actions must replay a game exactly") means a request just replays
those indices through the engine to reach the current state. No need to
(de)serialize the engine's frozen-dataclass tree at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from google.cloud import firestore

from engine.engine import NewGameConfig, apply, legal_actions, new_game
from engine.schema import GameData
from engine.state import GameState


@dataclass(frozen=True)
class GameRecord:
    player_ids: list[str]
    seed: int
    action_indices: list[int] = field(default_factory=list)


class GameStore(Protocol):
    def save(self, game_id: str, record: GameRecord) -> None: ...
    def load(self, game_id: str) -> GameRecord | None: ...


class InMemoryGameStore:
    """The default -- local dev and every test. No persistence across
    process restarts, same tradeoff the original in-memory dicts had."""

    def __init__(self) -> None:
        self._records: dict[str, GameRecord] = {}

    def save(self, game_id: str, record: GameRecord) -> None:
        self._records[game_id] = record

    def load(self, game_id: str) -> GameRecord | None:
        return self._records.get(game_id)


class FirestoreGameStore:
    """Production store. Collection name is namespaced so it can share
    the project's existing default Firestore database with other
    projects (e.g. TalkingLog) without colliding."""

    COLLECTION = "product_the_game_games"

    def __init__(self) -> None:
        self._client = firestore.Client()

    def save(self, game_id: str, record: GameRecord) -> None:
        doc = {
            "player_ids": record.player_ids,
            "seed": record.seed,
            "action_indices": record.action_indices,
        }
        self._client.collection(self.COLLECTION).document(game_id).set(doc)

    def load(self, game_id: str) -> GameRecord | None:
        snapshot = self._client.collection(self.COLLECTION).document(game_id).get()
        if not snapshot.exists:
            return None
        doc = snapshot.to_dict()
        return GameRecord(
            player_ids=doc["player_ids"],
            seed=doc["seed"],
            action_indices=doc["action_indices"],
        )


def replay(data: GameData, record: GameRecord) -> GameState:
    """Reconstruct the current GameState from scratch: new_game(), then
    apply() each stored action_index in order via that step's own
    legal_actions() -- exactly what a live game did originally."""
    state = new_game(NewGameConfig(data=data, player_ids=record.player_ids), record.seed)
    for index in record.action_indices:
        state = apply(state, legal_actions(state)[index])
    return state
