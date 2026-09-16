"""legal_actions, apply, is_over — the core turn state machine.

No card decks are wired in yet (steps 3 and 5): landing anywhere other than
a Milestone crossing is a no-op. This module only knows about movement,
Gateways, and Milestones.
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from typing import Literal

from engine.modifiers import qualifies
from engine.schema import Quadrant
from engine.state import BoardPosition, ConceptInstance, DVFTokens, GameState, PendingCross

WIN_TAM_THRESHOLD = 1.0  # $1B; TAM is stored in $B units
MAX_TURNS = 50
LOOP_SIZE = 16  # 1 Gateway (offset 0) + 15 coded spaces (offsets 1-15)


@dataclass(frozen=True)
class MoveConcept:
    concept_id: str
    direction: Literal["forward", "backward"]


@dataclass(frozen=True)
class CrossMilestone:
    concept_id: str
    cross: bool


Action = MoveConcept | CrossMilestone


@dataclass(frozen=True)
class Decision:
    kind: Literal["move", "cross_milestone"]
    owner: str
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class Outcome:
    result: Literal["win", "loss"]
    reason: str


def is_over(state: GameState) -> Outcome | None:
    if state.bank >= WIN_TAM_THRESHOLD:
        return Outcome("win", "TAM bank reached $1B")
    if state.turn >= MAX_TURNS:
        return Outcome("loss", "50 turns elapsed")
    if not state.portfolio:
        return Outcome("loss", "portfolio is empty with bank under $1B")
    return None


def _quadrant_by_id(state: GameState, quadrant_id: str) -> Quadrant:
    for q in state.data.board.quadrants:
        if q.id == quadrant_id:
            return q
    raise KeyError(f"unknown quadrant '{quadrant_id}'")


def _concept_by_id(state: GameState, concept_id: str) -> ConceptInstance:
    for c in state.portfolio:
        if c.card_id == concept_id:
            return c
    raise KeyError(f"no active concept '{concept_id}'")


def _replace_concept(
    state: GameState, new_instance: ConceptInstance
) -> tuple[ConceptInstance, ...]:
    return tuple(new_instance if c.card_id == new_instance.card_id else c for c in state.portfolio)


def legal_actions(state: GameState) -> list[Action]:
    if is_over(state) is not None:
        return []
    if state.pending_cross is not None:
        concept_id = state.pending_cross.concept_id
        return [CrossMilestone(concept_id, True), CrossMilestone(concept_id, False)]
    return [
        MoveConcept(c.card_id, direction)
        for c in state.portfolio
        for direction in ("forward", "backward")
    ]


def _roll_die(rng_state: tuple) -> tuple[int, tuple]:
    rng = random.Random()
    rng.setstate(rng_state)
    value = rng.randint(1, 6)
    return value, rng.getstate()


def _end_turn(state: GameState) -> GameState:
    """Finalize a resolved move/cross: stop if the game just ended, else
    advance to the next player's turn and roll their die."""
    if is_over(state) is not None:
        return state
    value, new_rng_state = _roll_die(state.rng_state)
    next_index = (state.active_player_index + 1) % len(state.players)
    return dataclasses.replace(
        state,
        turn=state.turn + 1,
        active_player_index=next_index,
        rng_state=new_rng_state,
        pending_roll=value,
        pending_cross=None,
    )


def apply(state: GameState, action: Action) -> GameState:
    if is_over(state) is not None:
        raise ValueError("game is already over")
    if isinstance(action, MoveConcept):
        return _apply_move(state, action)
    if isinstance(action, CrossMilestone):
        return _apply_cross(state, action)
    raise TypeError(f"unknown action type: {type(action)!r}")


def _apply_move(state: GameState, action: MoveConcept) -> GameState:
    if state.pending_cross is not None:
        raise ValueError("a cross-milestone decision is pending; resolve it first")
    if state.pending_roll is None:
        raise ValueError("no pending roll; not a move decision")

    instance = _concept_by_id(state, action.concept_id)
    card = state.data.concepts[instance.card_id]
    quadrant = _quadrant_by_id(state, instance.position.quadrant_id)
    n = state.pending_roll

    offset = instance.position.offset
    raw = offset + n if action.direction == "forward" else offset - n
    reaches_gateway = action.direction == "forward" and raw >= LOOP_SIZE

    if reaches_gateway and qualifies(instance, card, quadrant):
        milestone = quadrant.milestone
        next_quadrant_id = None if milestone.leads_to == "finish" else milestone.leads_to
        pending = PendingCross(
            concept_id=instance.card_id,
            same_quadrant_offset=raw % LOOP_SIZE,
            next_quadrant_id=next_quadrant_id,
        )
        return dataclasses.replace(state, pending_roll=None, pending_cross=pending)

    new_offset = raw % LOOP_SIZE
    new_instance = dataclasses.replace(
        instance, position=BoardPosition(instance.position.quadrant_id, new_offset)
    )
    moved_state = dataclasses.replace(
        state, portfolio=_replace_concept(state, new_instance), pending_roll=None
    )
    return _end_turn(moved_state)


def _apply_cross(state: GameState, action: CrossMilestone) -> GameState:
    pending = state.pending_cross
    if pending is None:
        raise ValueError("no pending cross-milestone decision")
    if action.concept_id != pending.concept_id:
        raise ValueError(f"cross decision is for '{pending.concept_id}', not '{action.concept_id}'")

    instance = _concept_by_id(state, action.concept_id)

    if not action.cross:
        new_instance = dataclasses.replace(
            instance,
            position=BoardPosition(instance.position.quadrant_id, pending.same_quadrant_offset),
        )
        resolved = dataclasses.replace(
            state, portfolio=_replace_concept(state, new_instance), pending_cross=None
        )
        return _end_turn(resolved)

    if pending.next_quadrant_id is None:
        card = state.data.concepts[instance.card_id]
        new_portfolio = tuple(c for c in state.portfolio if c.card_id != instance.card_id)
        resolved = dataclasses.replace(
            state, portfolio=new_portfolio, bank=state.bank + card.tam, pending_cross=None
        )
        return _end_turn(resolved)

    new_instance = dataclasses.replace(
        instance,
        position=BoardPosition(pending.next_quadrant_id, 0),
        tokens=DVFTokens(),
    )
    resolved = dataclasses.replace(
        state, portfolio=_replace_concept(state, new_instance), pending_cross=None
    )
    return _end_turn(resolved)
