"""legal_actions, apply, is_over — the core turn state machine.

D/V/F spaces draw from the landing Concept's current-quadrant sub-deck and
apply the card via engine/effects.py. Skills spaces draw for the active
player: an eligible Skill is taken automatically, an ineligible one pauses
for a discard/give decision (rules.md sec 10). Chance spaces and the
special handlers (Agile Methods, Scrum Master, role swaps) are still
no-ops (step 5, phases 2-3). After Move+Draw resolves, the team (PM) may
remove/draw Concepts any number of times in the Close phase before the
turn actually ends (rules.md sec 8.3).
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from typing import Literal

from engine.effects import apply_effects
from engine.modifiers import compute_skill_buffs, qualifies
from engine.schema import Quadrant
from engine.state import (
    BoardPosition,
    ConceptInstance,
    Deck,
    DVFTokens,
    GameState,
    PendingCross,
    entry_quadrant_id,
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


@dataclass(frozen=True)
class RemoveConcept:
    concept_id: str


@dataclass(frozen=True)
class DrawConcept:
    pass


@dataclass(frozen=True)
class EndClose:
    pass


@dataclass(frozen=True)
class DiscardSkill:
    pass


@dataclass(frozen=True)
class GiveSkill:
    recipient_id: str


Action = (
    MoveConcept | CrossMilestone | RemoveConcept | DrawConcept | EndClose | DiscardSkill | GiveSkill
)


@dataclass(frozen=True)
class Decision:
    kind: Literal["move", "cross_milestone", "close", "skill"]
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


def _deck_has_cards(deck: Deck) -> bool:
    return bool(deck.draw_pile) or bool(deck.discard_pile)


def legal_actions(state: GameState) -> list[Action]:
    if is_over(state) is not None:
        return []
    if state.pending_cross is not None:
        concept_id = state.pending_cross.concept_id
        return [CrossMilestone(concept_id, True), CrossMilestone(concept_id, False)]
    if state.pending_skill is not None:
        skill = state.data.skills[state.pending_skill]
        active_id = state.active_player.id
        actions: list[Action] = [DiscardSkill()]
        actions.extend(
            GiveSkill(p.id)
            for p in state.players
            if p.id != active_id and p.role_id in skill.eligible_roles
        )
        return actions
    if state.in_close_phase:
        actions: list[Action] = []
        if len(state.portfolio) > 1:
            actions.extend(RemoveConcept(c.card_id) for c in state.portfolio)
        if len(state.portfolio) < 5 and _deck_has_cards(state.concept_deck):
            actions.append(DrawConcept())
        actions.append(EndClose())
        return actions
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


def _draw_from_deck(deck: Deck, rng_state: tuple) -> tuple[str, Deck, tuple]:
    """Pop the top card, reshuffling the discard into a fresh draw pile first
    if needed. Raises if the deck has no cards at all, ever.

    The drawn card is *not* added to the discard pile here -- the caller
    decides that. A DVF card is used once and discarded immediately; a
    drawn Concept stays out of both piles, tracked in the Portfolio
    instead, until it's later removed.
    """
    draw_pile, discard_pile = deck.draw_pile, deck.discard_pile
    if not draw_pile:
        if not discard_pile:
            raise ValueError("deck has no cards defined at all")
        rng = random.Random()
        rng.setstate(rng_state)
        shuffled = list(discard_pile)
        rng.shuffle(shuffled)
        draw_pile, discard_pile = tuple(shuffled), ()
        rng_state = rng.getstate()

    card_id, remaining = draw_pile[0], draw_pile[1:]
    return card_id, Deck(remaining, discard_pile), rng_state


def _draw_dvf_card(state: GameState, quadrant_id: str, dim: str) -> tuple[str, GameState]:
    key = (quadrant_id, dim)
    deck = state.dvf_sub_decks.get(key)
    if deck is None:
        raise KeyError(f"no sub-deck for quadrant '{quadrant_id}' dim '{dim}'")
    try:
        card_id, new_deck, new_rng_state = _draw_from_deck(deck, state.rng_state)
    except ValueError as exc:
        raise ValueError(
            f"no cards defined for quadrant '{quadrant_id}' dim '{dim}' "
            f"(data/dvf/{quadrant_id}.yaml has none) -- see rules/open-questions.md"
        ) from exc
    new_deck = dataclasses.replace(new_deck, discard_pile=new_deck.discard_pile + (card_id,))
    new_sub_decks = {**state.dvf_sub_decks, key: new_deck}
    return card_id, dataclasses.replace(state, dvf_sub_decks=new_sub_decks, rng_state=new_rng_state)


def _draw_and_apply(state: GameState, concept_id: str, quadrant_id: str, dim: str) -> GameState:
    card_id, state = _draw_dvf_card(state, quadrant_id, dim)
    card = next(c for c in state.data.dvf_decks[quadrant_id].cards if c.id == card_id)
    return apply_effects(state, concept_id, card.effects)


def _give_skill_to_player(state: GameState, player_id: str, skill_id: str) -> GameState:
    """Set `skill_id` as `player_id`'s held Skill. A permanent Skill they
    already hold (if any) goes to the discard pile (rules.md sec 10)."""
    players = list(state.players)
    idx = next(i for i, p in enumerate(players) if p.id == player_id)
    old_skill_id = players[idx].skill_id
    players[idx] = dataclasses.replace(players[idx], skill_id=skill_id)

    skill_deck = state.skill_deck
    if old_skill_id is not None:
        skill_deck = dataclasses.replace(
            skill_deck, discard_pile=skill_deck.discard_pile + (old_skill_id,)
        )
    return dataclasses.replace(state, players=tuple(players), skill_deck=skill_deck)


def _draw_skill_and_resolve(state: GameState) -> GameState:
    """The active player draws a Skill card (rules.md sec 10).

    Eligible: taking it is automatic (see rules/open-questions.md #9).
    Ineligible: pauses for a discard-or-give decision -- doesn't enter
    Close phase yet (`_enter_close_phase` checks `pending_skill`).
    """
    try:
        card_id, new_deck, new_rng_state = _draw_from_deck(state.skill_deck, state.rng_state)
    except ValueError as exc:
        raise ValueError(
            "no Skill cards defined at all (data/skills.yaml has none) "
            "-- see rules/open-questions.md"
        ) from exc
    state = dataclasses.replace(state, skill_deck=new_deck, rng_state=new_rng_state)

    skill = state.data.skills[card_id]
    if state.active_player.role_id in skill.eligible_roles:
        return _give_skill_to_player(state, state.active_player.id, card_id)
    return dataclasses.replace(state, pending_skill=card_id)


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
    if space_type == "skills":
        return _draw_skill_and_resolve(state)
    if space_type not in ("D", "V", "F"):
        return state  # chance: phase 2 of this step

    return _draw_and_apply(state, concept_id, quadrant_id, space_type)


def _enter_close_phase(state: GameState) -> GameState:
    """Move+Draw is done for this turn. Every turn gets a Close phase
    (rules.md sec 8.3), regardless of what happened during Move/Draw --
    unless the game just ended (e.g. Finish completed the bank), or an
    ineligible drawn Skill is still awaiting a discard/give decision."""
    if is_over(state) is not None:
        return state
    if state.pending_skill is not None:
        return state
    return dataclasses.replace(state, in_close_phase=True)


def apply(state: GameState, action: Action) -> GameState:
    if is_over(state) is not None:
        raise ValueError("game is already over")
    if isinstance(action, MoveConcept):
        return _apply_move(state, action)
    if isinstance(action, CrossMilestone):
        return _apply_cross(state, action)
    if isinstance(action, RemoveConcept):
        return _apply_remove_concept(state, action)
    if isinstance(action, DrawConcept):
        return _apply_draw_concept(state)
    if isinstance(action, EndClose):
        return _apply_end_close(state)
    if isinstance(action, DiscardSkill):
        return _apply_discard_skill(state)
    if isinstance(action, GiveSkill):
        return _apply_give_skill(state, action)
    raise TypeError(f"unknown action type: {type(action)!r}")


def _require_close_phase(state: GameState) -> None:
    if not state.in_close_phase:
        raise ValueError("not in the Close phase")


def _require_pending_skill(state: GameState) -> str:
    if state.pending_skill is None:
        raise ValueError("no pending Skill decision")
    return state.pending_skill


def _apply_discard_skill(state: GameState) -> GameState:
    skill_id = _require_pending_skill(state)
    new_deck = dataclasses.replace(
        state.skill_deck, discard_pile=state.skill_deck.discard_pile + (skill_id,)
    )
    state = dataclasses.replace(state, skill_deck=new_deck, pending_skill=None)
    return _enter_close_phase(state)


def _apply_give_skill(state: GameState, action: GiveSkill) -> GameState:
    skill_id = _require_pending_skill(state)
    if action.recipient_id == state.active_player.id:
        raise ValueError("cannot give a Skill to yourself")
    recipient = next((p for p in state.players if p.id == action.recipient_id), None)
    if recipient is None:
        raise KeyError(f"no player '{action.recipient_id}'")
    skill = state.data.skills[skill_id]
    if recipient.role_id not in skill.eligible_roles:
        raise ValueError(f"'{action.recipient_id}' is not eligible for this Skill")

    state = _give_skill_to_player(state, action.recipient_id, skill_id)
    state = dataclasses.replace(state, pending_skill=None)
    # rules.md sec 10: the active player's turn ends immediately, no Close phase.
    return _end_turn(state)


def _apply_remove_concept(state: GameState, action: RemoveConcept) -> GameState:
    _require_close_phase(state)
    if len(state.portfolio) <= 1:
        raise ValueError("cannot remove the last active Concept")
    instance = get_concept(state, action.concept_id)
    new_portfolio = tuple(c for c in state.portfolio if c.card_id != instance.card_id)
    new_deck = dataclasses.replace(
        state.concept_deck, discard_pile=state.concept_deck.discard_pile + (instance.card_id,)
    )
    return dataclasses.replace(state, portfolio=new_portfolio, concept_deck=new_deck)


def _apply_draw_concept(state: GameState) -> GameState:
    _require_close_phase(state)
    if len(state.portfolio) >= 5:
        raise ValueError("Portfolio already has 5 active Concepts")
    try:
        card_id, new_deck, new_rng_state = _draw_from_deck(state.concept_deck, state.rng_state)
    except ValueError as exc:
        raise ValueError("no Concepts left to draw") from exc
    new_instance = ConceptInstance(
        card_id=card_id,
        position=BoardPosition(entry_quadrant_id(state.data), 0),
    )
    return dataclasses.replace(
        state,
        portfolio=state.portfolio + (new_instance,),
        concept_deck=new_deck,
        rng_state=new_rng_state,
    )


def _apply_end_close(state: GameState) -> GameState:
    _require_close_phase(state)
    return _end_turn(dataclasses.replace(state, in_close_phase=False))


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

    if reaches_gateway and qualifies(instance, card, quadrant, compute_skill_buffs(state, card)):
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
    return _enter_close_phase(state)


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
        return _enter_close_phase(state)

    if pending.next_quadrant_id is None:
        card = state.data.concepts[instance.card_id]
        new_portfolio = tuple(c for c in state.portfolio if c.card_id != instance.card_id)
        resolved = dataclasses.replace(
            state, portfolio=new_portfolio, bank=state.bank + card.tam, pending_cross=None
        )
        return _enter_close_phase(resolved)

    new_instance = dataclasses.replace(
        instance,
        position=BoardPosition(pending.next_quadrant_id, 0),
        tokens=DVFTokens(),
    )
    resolved = dataclasses.replace(with_concept(state, new_instance), pending_cross=None)
    return _enter_close_phase(resolved)
