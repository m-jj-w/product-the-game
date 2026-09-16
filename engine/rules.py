"""legal_actions, apply, is_over — the core turn state machine.

Skills and Chance spaces are still no-ops (step 5); D/V/F spaces draw from
the landing Concept's current-quadrant sub-deck and apply the card via
engine/effects.py.
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from typing import Literal

from engine.effects import apply_effects
from engine.modifiers import qualifies
from engine.schema import Quadrant
from engine.state import (
    BoardPosition,
    DVFTokens,
    GameState,
    PendingCross,
    SubDeck,
    get_concept,
    with_concept,
)

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


def _draw_card(
    sub_decks: dict[tuple[str, str], SubDeck], rng_state: tuple, quadrant_id: str, dim: str
) -> tuple[str, dict[tuple[str, str], SubDeck], tuple]:
    key = (quadrant_id, dim)
    deck = sub_decks.get(key)
    if deck is None:
        raise KeyError(f"no sub-deck for quadrant '{quadrant_id}' dim '{dim}'")

    draw_pile, discard_pile = deck.draw_pile, deck.discard_pile
    if not draw_pile:
        if not discard_pile:
            raise ValueError(
                f"no cards defined for quadrant '{quadrant_id}' dim '{dim}' "
                f"(data/dvf/{quadrant_id}.yaml has none) -- see rules/open-questions.md"
            )
        rng = random.Random()
        rng.setstate(rng_state)
        shuffled = list(discard_pile)
        rng.shuffle(shuffled)
        draw_pile, discard_pile = tuple(shuffled), ()
        rng_state = rng.getstate()

    card_id, remaining = draw_pile[0], draw_pile[1:]
    new_sub_decks = {**sub_decks, key: SubDeck(remaining, discard_pile + (card_id,))}
    return card_id, new_sub_decks, rng_state


def _draw_and_apply(state: GameState, concept_id: str, quadrant_id: str, dim: str) -> GameState:
    card_id, new_sub_decks, new_rng_state = _draw_card(
        state.dvf_sub_decks, state.rng_state, quadrant_id, dim
    )
    state = dataclasses.replace(state, dvf_sub_decks=new_sub_decks, rng_state=new_rng_state)
    card = next(c for c in state.data.dvf_decks[quadrant_id].cards if c.id == card_id)
    return apply_effects(state, concept_id, card.effects)


def _finalize_position(state: GameState, concept_id: str, new_offset: int) -> GameState:
    """Land a Concept at `new_offset` in its current quadrant, then trigger
    whatever's there. Offset 0 is the Gateway: no draw, ever (rules.md sec 4)."""
    instance = get_concept(state, concept_id)
    quadrant_id = instance.position.quadrant_id
    state = with_concept(
        state, dataclasses.replace(instance, position=BoardPosition(quadrant_id, new_offset))
    )
    if new_offset == 0:
        return state

    quadrant = _quadrant_by_id(state, quadrant_id)
    space_type = quadrant.spaces[new_offset - 1]
    if space_type not in ("D", "V", "F"):
        return state  # skills/chance: step 5

    return _draw_and_apply(state, concept_id, quadrant_id, space_type)


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

    instance = get_concept(state, action.concept_id)
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

    state = dataclasses.replace(state, pending_roll=None)
    state = _finalize_position(state, instance.card_id, raw % LOOP_SIZE)
    return _end_turn(state)


def _apply_cross(state: GameState, action: CrossMilestone) -> GameState:
    pending = state.pending_cross
    if pending is None:
        raise ValueError("no pending cross-milestone decision")
    if action.concept_id != pending.concept_id:
        raise ValueError(f"cross decision is for '{pending.concept_id}', not '{action.concept_id}'")

    instance = get_concept(state, action.concept_id)

    if not action.cross:
        state = dataclasses.replace(state, pending_cross=None)
        state = _finalize_position(state, instance.card_id, pending.same_quadrant_offset)
        return _end_turn(state)

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
    resolved = dataclasses.replace(with_concept(state, new_instance), pending_cross=None)
    return _end_turn(resolved)
