"""Where games live between requests, and how their history is narrated.

Stores the seed plus the sequence of chosen action indices (and when each
was chosen), not a serialized GameState -- CLAUDE.md's own invariant ("a
seed plus a list of actions must replay a game exactly") means a request
just replays those indices through the engine to reach the current state.
No need to (de)serialize the engine's frozen-dataclass tree at all, and
narrating each step along the way comes for free from the same replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from google.cloud import firestore

from agents.llm_agent import SPACE_LABELS, describe_action
from engine.engine import NewGameConfig, apply, legal_actions, new_game
from engine.rules import Action, CrossMilestone, MoveConcept
from engine.schema import GameData
from engine.state import GameState, get_concept


@dataclass(frozen=True)
class GameRecord:
    player_ids: list[str]
    seed: int
    action_indices: list[int] = field(default_factory=list)
    action_timestamps: list[str] = field(default_factory=list)  # ISO 8601, parallel array


@dataclass(frozen=True)
class HistoryEntry:
    turn: int
    text: str
    at: str  # ISO 8601


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
            "action_timestamps": record.action_timestamps,
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
            action_timestamps=doc.get("action_timestamps", []),
        )


def narrate_step(old_state: GameState, new_state: GameState, action: Action) -> str:
    """A past-tense line describing what `action` just did -- for the web
    UI's History panel. Falls back to the action's own (already past-
    tense-ish) description for anything not specially handled below."""
    if isinstance(action, MoveConcept):
        instance = get_concept(new_state, action.concept_id)
        card = new_state.data.concepts[instance.card_id]
        if instance.position.offset == 0:
            return f"{card.name} landed on the Gateway."

        quadrant = new_state.data.board.quadrant(instance.position.quadrant_id)
        space_type = quadrant.spaces[instance.position.offset - 1]
        label = SPACE_LABELS[space_type]

        if space_type in ("D", "V", "F"):
            deck = new_state.dvf_sub_decks[(quadrant.id, space_type)]
            drawn_id = deck.discard_pile[-1]
            drawn_name = next(
                c.name for c in new_state.data.dvf_decks[quadrant.id].cards if c.id == drawn_id
            )
            return f"{card.name} landed on a {label} space and drew '{drawn_name}'!"

        if space_type == "chance":
            drawn_id = new_state.chance_deck.discard_pile[-1]
            drawn_name = new_state.data.chance_cards[drawn_id].name
            return f"{card.name} landed on a {label} space and drew '{drawn_name}'!"

        # skills: drawn for the active player, not the Concept itself
        if new_state.pending_skill is not None:
            skill_name = new_state.data.skills[new_state.pending_skill].name
            return f"{card.name} landed on a {label} space -- drew '{skill_name}' (not eligible)."
        old_skills = {p.id: p.skill_id for p in old_state.players}
        newly_skilled = next(
            (p for p in new_state.players if p.skill_id and p.skill_id != old_skills.get(p.id)),
            None,
        )
        if newly_skilled is not None:
            skill_name = new_state.data.skills[newly_skilled.skill_id].name
            return (
                f"{card.name} landed on a {label} space -- {newly_skilled.id} drew '{skill_name}'!"
            )
        return f"{card.name} landed on a {label} space."

    if isinstance(action, CrossMilestone):
        card = new_state.data.concepts[action.concept_id]
        if not action.cross:
            return f"{card.name} declined to cross the Milestone."
        still_active = any(c.card_id == action.concept_id for c in new_state.portfolio)
        if not still_active:
            return f"{card.name} reached Finish and banked ${card.tam:.2f}B!"
        instance = get_concept(new_state, action.concept_id)
        quadrant = new_state.data.board.quadrant(instance.position.quadrant_id)
        return f"{card.name} crossed into {quadrant.name}!"

    return describe_action(action, old_state)


def replay_with_history(data: GameData, record: GameRecord) -> tuple[GameState, list[HistoryEntry]]:
    """Reconstruct the current GameState from scratch -- new_game(), then
    apply() each stored action_index in order via that step's own
    legal_actions(), exactly what a live game did originally -- while also
    narrating each step for the History panel. Newest-last; callers that
    want "latest first" reverse it."""
    state = new_game(NewGameConfig(data=data, player_ids=record.player_ids), record.seed)
    history: list[HistoryEntry] = []
    for index, timestamp in zip(record.action_indices, record.action_timestamps, strict=True):
        action = legal_actions(state)[index]
        new_state = apply(state, action)
        history.append(
            HistoryEntry(
                turn=new_state.turn, text=narrate_step(state, new_state, action), at=timestamp
            )
        )
        state = new_state
    return state, history
