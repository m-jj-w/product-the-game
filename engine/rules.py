"""legal_actions, apply, is_over — the core turn state machine.

D/V/F spaces draw from the landing Concept's current-quadrant sub-deck and
apply the card via engine/effects.py. Skills spaces draw for the active
player: an eligible Skill is taken automatically, an ineligible one pauses
for a discard/give decision (rules.md sec 10). Chance spaces draw a Chance
card and apply it to the landing Concept -- except a remove_concept effect
(the schema only allows `chooser: "team"`), which pauses for the team's
target choice instead. After Move+Draw resolves, the team (PM) may
remove/draw Concepts, and (once every active Concept has passed Product
Market Fit) swap two players' roles, any number of times in the Close
phase before the turn actually ends (rules.md sec 8.3).

Two special Skills change the turn state machine itself rather than
buffing a Concept: Agile Methods grants its holder a second complete
Move-Draw-Close cycle before the turn actually advances (`_end_turn`'s
`agile_bonus_pending`); Scrum Master lets its holder delegate whatever
decision they currently own to another player (`DelegateTurn`) -- turn
order still rotates from the original holder's seat afterward, not the
delegate's (`turn_owner_index`, resolved with the user --
rules/open-questions.md #8).
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from typing import Literal

from engine.effects import apply_effects
from engine.modifiers import compute_skill_buffs, qualifies, required_dvf
from engine.schema import ChanceCard, Quadrant
from engine.state import (
    BoardPosition,
    ConceptInstance,
    Deck,
    DVFTokens,
    GameState,
    PendingCross,
    Player,
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


@dataclass(frozen=True)
class ChanceRemoveConcept:
    concept_id: str


@dataclass(frozen=True)
class DelegateTurn:
    """Scrum Master: hand the rest of this turn to another player."""

    recipient_id: str


@dataclass(frozen=True)
class RoleSwap:
    """The team-earned swap, once every active Concept has passed PMF."""

    player_a_id: str
    player_b_id: str


@dataclass(frozen=True)
class ResearchBreakthrough:
    """Research Breakthrough (Chance): top up one Concept's chosen
    dimension to whatever the next Milestone in its current quadrant
    requires."""

    concept_id: str
    dim: Literal["D", "V", "F"]


Action = (
    MoveConcept
    | CrossMilestone
    | RemoveConcept
    | DrawConcept
    | EndClose
    | DiscardSkill
    | GiveSkill
    | ChanceRemoveConcept
    | DelegateTurn
    | RoleSwap
    | ResearchBreakthrough
)


@dataclass(frozen=True)
class Decision:
    kind: Literal[
        "move", "cross_milestone", "close", "skill", "chance_removal", "research_breakthrough"
    ]
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


def _holds_special(state: GameState, player: Player, handler: str) -> bool:
    if player.skill_id is None:
        return False
    skill = state.data.skills[player.skill_id]
    return any(effect.type == "special" and effect.handler == handler for effect in skill.effects)


def _scrum_master_options(state: GameState) -> list[Action]:
    """rules.md sec 10: usable at any point in the holder's own turn, to
    hand the rest of it to another player. Only offered on decisions the
    active player currently owns -- not Close/Chance-removal, which are
    always PM-owned regardless of who's active."""
    if not _holds_special(state, state.active_player, "scrum_master"):
        return []
    return [DelegateTurn(p.id) for p in state.players if p.id != state.active_player.id]


def _role_swap_condition_met(state: GameState) -> bool:
    """rules.md sec 3: every active Concept has passed the Product Market
    Fit Milestone (NPD -> Scaling), i.e. is in a quadrant of order >= 3."""
    return bool(state.portfolio) and all(
        _quadrant_by_id(state, c.position.quadrant_id).order >= 3 for c in state.portfolio
    )


def _role_swap_offered(state: GameState) -> bool:
    return (
        not state.role_swap_used
        and not state.role_swap_forfeited
        and _role_swap_condition_met(state)
    )


def legal_actions(state: GameState) -> list[Action]:
    if is_over(state) is not None:
        return []
    if state.pending_cross is not None:
        concept_id = state.pending_cross.concept_id
        actions: list[Action] = [
            CrossMilestone(concept_id, True),
            CrossMilestone(concept_id, False),
        ]
        return actions + _scrum_master_options(state)
    if state.pending_skill is not None:
        skill = state.data.skills[state.pending_skill]
        active_id = state.active_player.id
        actions = [DiscardSkill()]
        actions.extend(
            GiveSkill(p.id)
            for p in state.players
            if p.id != active_id and p.role_id in skill.eligible_roles
        )
        return actions + _scrum_master_options(state)
    if state.pending_chance_removal:
        return [ChanceRemoveConcept(c.card_id) for c in state.portfolio]
    if state.pending_research_breakthrough:
        return [
            ResearchBreakthrough(c.card_id, dim) for c in state.portfolio for dim in ("D", "V", "F")
        ]
    if state.in_close_phase:
        actions = []
        if len(state.portfolio) > 1:
            actions.extend(RemoveConcept(c.card_id) for c in state.portfolio)
        if len(state.portfolio) < state.portfolio_capacity and _deck_has_cards(state.concept_deck):
            actions.append(DrawConcept())
        if _role_swap_offered(state):
            actions.extend(
                RoleSwap(a.id, b.id)
                for i, a in enumerate(state.players)
                for b in state.players[i + 1 :]
            )
        actions.append(EndClose())
        return actions
    move_actions: list[Action] = [
        MoveConcept(c.card_id, direction)
        for c in state.portfolio
        for direction in ("forward", "backward")
    ]
    return move_actions + _scrum_master_options(state)


def _roll_die(rng_state: tuple) -> tuple[int, tuple]:
    rng = random.Random()
    rng.setstate(rng_state)
    value = rng.randint(1, 6)
    return value, rng.getstate()


def _end_turn(state: GameState) -> GameState:
    """Finalize a resolved move/cross/close/give: stop if the game just
    ended. Otherwise, either grant the turn owner a bonus cycle (rules.md
    sec 10: two complete turns count as one) -- from Agile Methods or a
    Productivity/Retrospective Chance card, indistinguishable once
    queued -- or actually conclude the turn: advance turn/turn_owner_index,
    roll the next die. A Retrospective-queued bonus for the *next* owner
    (`pending_double_next_turn`) is carried forward and converted to
    `pending_extra_turn` on the new owner, so it fires on their own
    `_end_turn` rather than this one.

    Rotation always keys off `turn_owner_index`, not `active_player_index`:
    a Scrum Master delegation mid-turn only reassigns who's deciding, so
    it never affects whose turn slot comes next (rules/open-questions.md
    #8) or who's checked for Agile Methods.
    """
    if is_over(state) is not None:
        return state

    if not state.agile_bonus_pending and (
        _holds_special(state, state.turn_owner, "agile_methods") or state.pending_extra_turn
    ):
        value, new_rng_state = _roll_die(state.rng_state)
        return dataclasses.replace(
            state,
            active_player_index=state.turn_owner_index,
            rng_state=new_rng_state,
            pending_roll=value,
            pending_cross=None,
            agile_bonus_pending=True,
            pending_extra_turn=False,
        )

    value, new_rng_state = _roll_die(state.rng_state)
    next_index = (state.turn_owner_index + 1) % len(state.players)
    return dataclasses.replace(
        state,
        turn=state.turn + 1,
        active_player_index=next_index,
        turn_owner_index=next_index,
        rng_state=new_rng_state,
        pending_roll=value,
        pending_cross=None,
        agile_bonus_pending=False,
        pending_extra_turn=state.pending_double_next_turn,
        pending_double_next_turn=False,
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


def _draw_chance_card(state: GameState) -> tuple[ChanceCard, GameState]:
    """Draw a Chance card. The card itself is used up and discarded
    immediately (like a DVF card) regardless of what its effect needs --
    only the effect's *target* might still need a decision."""
    try:
        card_id, new_deck, new_rng_state = _draw_from_deck(state.chance_deck, state.rng_state)
    except ValueError as exc:
        raise ValueError(
            "no Chance cards defined at all (data/chance.yaml has none) "
            "-- see rules/open-questions.md"
        ) from exc
    new_deck = dataclasses.replace(new_deck, discard_pile=new_deck.discard_pile + (card_id,))
    state = dataclasses.replace(state, chance_deck=new_deck, rng_state=new_rng_state)
    return state.data.chance_cards[card_id], state


def _fetch_concept_from_deck(deck: Deck, target_id: str) -> tuple[bool, Deck]:
    """Search both piles for one specific Concept id (Fetch Concept's Chance
    effect), rather than `_draw_from_deck`'s usual random top-of-pile draw.
    A previously-removed target sits in `discard_pile`, not `draw_pile`."""
    if target_id in deck.draw_pile:
        new_pile = tuple(cid for cid in deck.draw_pile if cid != target_id)
        return True, dataclasses.replace(deck, draw_pile=new_pile)
    if target_id in deck.discard_pile:
        new_discard = tuple(cid for cid in deck.discard_pile if cid != target_id)
        return True, dataclasses.replace(deck, discard_pile=new_discard)
    return False, deck


def _add_concept_to_portfolio(state: GameState, card_id: str) -> GameState:
    new_instance = ConceptInstance(
        card_id=card_id, position=BoardPosition(entry_quadrant_id(state.data), 0)
    )
    return dataclasses.replace(state, portfolio=state.portfolio + (new_instance,))


def _apply_chance_special(state: GameState, handler: str, target: str | None) -> GameState:
    """Chance-card-triggered mechanics that change turn/Portfolio state
    directly rather than buffing the landing Concept -- see
    rules/open-questions.md for each one's provisional semantics. None of
    these cards combine a special effect with anything else (same
    assumption `_resolve_chance_card` already makes for remove_concept)."""
    if handler == "sick_day":
        return dataclasses.replace(state, pending_skip_close=True)
    if handler == "productivity":
        return dataclasses.replace(state, pending_extra_turn=True)
    if handler == "retrospective":
        return dataclasses.replace(state, pending_double_next_turn=True)
    if handler == "expand_portfolio":
        return dataclasses.replace(state, portfolio_capacity=state.portfolio_capacity + 1)
    if handler == "narrow_portfolio":
        new_capacity = max(1, state.portfolio_capacity - 1)
        state = dataclasses.replace(state, portfolio_capacity=new_capacity)
        if len(state.portfolio) > new_capacity:
            return dataclasses.replace(state, pending_chance_removal=True)
        return state
    if handler == "research_breakthrough":
        return dataclasses.replace(state, pending_research_breakthrough=True)
    if handler == "fetch_concept":
        assert target is not None  # schema's cross-reference check guarantees this
        found, new_deck = _fetch_concept_from_deck(state.concept_deck, target)
        state = dataclasses.replace(state, concept_deck=new_deck)
        if not found:
            return state  # already active, or somehow not in either pile -- fizzles
        if len(state.portfolio) >= state.portfolio_capacity:
            return dataclasses.replace(
                state, pending_chance_removal=True, pending_concept_to_add=target
            )
        return _add_concept_to_portfolio(state, target)
    raise ValueError(f"unknown Chance special handler '{handler}'")


def _resolve_chance_card(state: GameState, concept_id: str, card: ChanceCard) -> GameState:
    """rules.md sec 8.2: a Chance card affects the landing Concept unless
    it says otherwise. `remove_concept` always says otherwise -- the
    schema only allows `chooser: "team"`, so it always pauses for the
    team's choice of target instead of a direct apply. A `special` effect
    likewise bypasses `apply_effects` (engine/effects.py doesn't handle it)
    and goes through its own dispatch."""
    if any(effect.type == "remove_concept" for effect in card.effects):
        return dataclasses.replace(state, pending_chance_removal=True)
    for effect in card.effects:
        if effect.type == "special":
            return _apply_chance_special(state, effect.handler, effect.target)
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
    if space_type == "skills":
        return _draw_skill_and_resolve(state)
    if space_type == "chance":
        card, state = _draw_chance_card(state)
        return _resolve_chance_card(state, concept_id, card)
    if space_type not in ("D", "V", "F"):
        return state

    return _draw_and_apply(state, concept_id, quadrant_id, space_type)


def _enter_close_phase(state: GameState) -> GameState:
    """Move+Draw is done for this turn. Every turn gets a Close phase
    (rules.md sec 8.3), regardless of what happened during Move/Draw --
    unless the game just ended (e.g. Finish completed the bank), an
    ineligible drawn Skill is awaiting a discard/give decision, or a
    Chance card is awaiting the team's removal target."""
    if is_over(state) is not None:
        return state
    if state.pending_skill is not None:
        return state
    if state.pending_chance_removal:
        return state
    if state.pending_research_breakthrough:
        return state
    if state.pending_skip_close:
        return _end_turn(dataclasses.replace(state, pending_skip_close=False))
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
    if isinstance(action, ChanceRemoveConcept):
        return _apply_chance_remove_concept(state, action)
    if isinstance(action, DelegateTurn):
        return _apply_delegate_turn(state, action)
    if isinstance(action, RoleSwap):
        return _apply_role_swap(state, action)
    if isinstance(action, ResearchBreakthrough):
        return _apply_research_breakthrough(state, action)
    raise TypeError(f"unknown action type: {type(action)!r}")


def _apply_delegate_turn(state: GameState, action: DelegateTurn) -> GameState:
    if state.in_close_phase or state.pending_chance_removal:
        raise ValueError("Scrum Master can't delegate a Team-owned decision")
    if not _holds_special(state, state.active_player, "scrum_master"):
        raise ValueError(f"'{state.active_player.id}' does not hold Scrum Master")
    if action.recipient_id == state.active_player.id:
        raise ValueError("cannot delegate to yourself")
    recipient = next((p for p in state.players if p.id == action.recipient_id), None)
    if recipient is None:
        raise KeyError(f"no player '{action.recipient_id}'")
    return dataclasses.replace(state, active_player_index=state.players.index(recipient))


def _apply_role_swap(state: GameState, action: RoleSwap) -> GameState:
    _require_close_phase(state)
    if not _role_swap_offered(state):
        raise ValueError("no role swap is available")
    if action.player_a_id == action.player_b_id:
        raise ValueError("cannot swap a player's role with themselves")
    players = list(state.players)
    idx_a = next(i for i, p in enumerate(players) if p.id == action.player_a_id)
    idx_b = next(i for i, p in enumerate(players) if p.id == action.player_b_id)
    role_a, role_b = players[idx_a].role_id, players[idx_b].role_id
    players[idx_a] = dataclasses.replace(players[idx_a], role_id=role_b)
    players[idx_b] = dataclasses.replace(players[idx_b], role_id=role_a)
    return dataclasses.replace(state, players=tuple(players), role_swap_used=True)


def _apply_chance_remove_concept(state: GameState, action: ChanceRemoveConcept) -> GameState:
    if not state.pending_chance_removal:
        raise ValueError("no pending Chance removal decision")
    instance = get_concept(state, action.concept_id)
    new_portfolio = tuple(c for c in state.portfolio if c.card_id != instance.card_id)
    new_deck = dataclasses.replace(
        state.concept_deck, discard_pile=state.concept_deck.discard_pile + (instance.card_id,)
    )
    state = dataclasses.replace(
        state, portfolio=new_portfolio, concept_deck=new_deck, pending_chance_removal=False
    )
    # Fetch Concept's forced-discard-then-add sequence: this discard may
    # have been to make room, in which case the fetched concept still
    # needs to land in the Portfolio.
    if state.pending_concept_to_add is not None:
        state = _add_concept_to_portfolio(state, state.pending_concept_to_add)
        state = dataclasses.replace(state, pending_concept_to_add=None)
    # No minimum-1 floor here (unlike Close-phase RemoveConcept): rules.md
    # sec 2 explicitly allows Budget Cuts to remove the last Concept and
    # end the game -- _enter_close_phase's is_over check handles that.
    return _enter_close_phase(state)


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
    if len(state.portfolio) >= state.portfolio_capacity:
        raise ValueError(f"Portfolio already has {state.portfolio_capacity} active Concepts")
    try:
        card_id, new_deck, new_rng_state = _draw_from_deck(state.concept_deck, state.rng_state)
    except ValueError as exc:
        raise ValueError("no Concepts left to draw") from exc
    state = dataclasses.replace(state, concept_deck=new_deck, rng_state=new_rng_state)
    return _add_concept_to_portfolio(state, card_id)


def _apply_research_breakthrough(state: GameState, action: ResearchBreakthrough) -> GameState:
    if not state.pending_research_breakthrough:
        raise ValueError("no pending Research Breakthrough decision")
    instance = get_concept(state, action.concept_id)
    card = state.data.concepts[instance.card_id]
    quadrant = _quadrant_by_id(state, instance.position.quadrant_id)
    required = required_dvf(card, quadrant)
    have = getattr(instance.tokens, action.dim)
    gain = max(0, getattr(required, action.dim) - have)
    new_tokens = dataclasses.replace(instance.tokens, **{action.dim: have + gain})
    state = with_concept(state, dataclasses.replace(instance, tokens=new_tokens))
    state = dataclasses.replace(state, pending_research_breakthrough=False)
    return _enter_close_phase(state)


def _apply_end_close(state: GameState) -> GameState:
    _require_close_phase(state)
    # rules.md sec 3: an offered-but-unused swap is lost, permanently --
    # even though the quadrant condition will typically stay true forever
    # after (rules/open-questions.md #12).
    if _role_swap_offered(state):
        state = dataclasses.replace(state, role_swap_forfeited=True)
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
