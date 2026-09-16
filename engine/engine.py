"""Public engine API — see CLAUDE.md's "Public engine API" section.

Agents, the UI, and the server talk to the game only through this module.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from engine.rules import (
    Action,
    CrossMilestone,
    Decision,
    DiscardSkill,
    DrawConcept,
    EndClose,
    GiveSkill,
    MoveConcept,
    Outcome,
    RemoveConcept,
    apply,
    is_over,
    legal_actions,
)
from engine.schema import GameData
from engine.state import (
    BoardPosition,
    ConceptInstance,
    Deck,
    GameState,
    Player,
    entry_quadrant_id,
)

__all__ = [
    "Action",
    "CrossMilestone",
    "Decision",
    "DiscardSkill",
    "DrawConcept",
    "EndClose",
    "GiveSkill",
    "MoveConcept",
    "NewGameConfig",
    "Outcome",
    "RemoveConcept",
    "apply",
    "current_decision",
    "is_over",
    "legal_actions",
    "new_game",
    "observe",
]

STARTING_PORTFOLIO_SIZE = 5


@dataclass(frozen=True)
class NewGameConfig:
    data: GameData
    player_ids: list[str]


def new_game(config: NewGameConfig, seed: int) -> GameState:
    """Set up a new game: assign roles, draw the starting Portfolio, roll for turn 1."""
    if not 1 <= len(config.player_ids) <= 5:
        raise ValueError(f"player_ids must have 1-5 entries, got {len(config.player_ids)}")
    if "pm" not in config.data.roles:
        raise ValueError("data has no role with id 'pm'")
    if len(config.data.roles) < len(config.player_ids):
        raise ValueError(
            f"not enough roles ({len(config.data.roles)}) for {len(config.player_ids)} players"
        )
    if len(config.data.concepts) < STARTING_PORTFOLIO_SIZE:
        raise ValueError(
            f"data has {len(config.data.concepts)} concepts; need at least "
            f"{STARTING_PORTFOLIO_SIZE} distinct concepts to draw a starting Portfolio"
        )

    rng = random.Random(seed)

    shuffled_players = list(config.player_ids)
    rng.shuffle(shuffled_players)
    pm_player, other_players = shuffled_players[0], shuffled_players[1:]

    other_roles = [r for r in config.data.roles if r != "pm"]
    rng.shuffle(other_roles)
    role_by_player = {pm_player: "pm"}
    role_by_player.update(zip(other_players, other_roles, strict=False))

    players = tuple(Player(id=pid, role_id=role_by_player[pid]) for pid in config.player_ids)
    active_player_index = config.player_ids.index(pm_player)

    concept_ids = list(config.data.concepts)
    rng.shuffle(concept_ids)
    starting_ids = concept_ids[:STARTING_PORTFOLIO_SIZE]
    remaining_ids = concept_ids[STARTING_PORTFOLIO_SIZE:]
    entry_id = entry_quadrant_id(config.data)
    portfolio = tuple(
        ConceptInstance(card_id=cid, position=BoardPosition(quadrant_id=entry_id, offset=0))
        for cid in starting_ids
    )
    concept_deck = Deck(draw_pile=tuple(remaining_ids))

    sub_decks = _build_initial_sub_decks(config.data, rng)
    skill_deck = _build_shuffled_deck(config.data.skills, rng)
    roll = rng.randint(1, 6)

    return GameState(
        data=config.data,
        turn=0,
        active_player_index=active_player_index,
        turn_owner_index=active_player_index,
        players=players,
        portfolio=portfolio,
        bank=0.0,
        rng_state=rng.getstate(),
        dvf_sub_decks=sub_decks,
        concept_deck=concept_deck,
        skill_deck=skill_deck,
        pending_roll=roll,
        pending_cross=None,
    )


def _build_shuffled_deck(card_ids: dict[str, object], rng: random.Random) -> Deck:
    ids = list(card_ids)
    rng.shuffle(ids)
    return Deck(draw_pile=tuple(ids))


def _build_initial_sub_decks(data: GameData, rng: random.Random) -> dict[tuple[str, str], Deck]:
    sub_decks: dict[tuple[str, str], Deck] = {}
    for quadrant in data.board.quadrants:
        deck = data.dvf_decks.get(quadrant.id)
        cards = deck.cards if deck is not None else []
        for dim in ("D", "V", "F"):
            card_ids = [c.id for c in cards if c.dim == dim]
            rng.shuffle(card_ids)
            sub_decks[(quadrant.id, dim)] = Deck(draw_pile=tuple(card_ids))
    return sub_decks


def current_decision(state: GameState) -> Decision | None:
    """What's being decided and who decides it. None once is_over(state) is set.

    Close-phase decisions are owned by the PM, not necessarily the active
    player (CLAUDE.md's decision table: "Team (PM decides)")."""
    if is_over(state) is not None:
        return None
    if state.pending_cross is not None:
        kind, owner = "cross_milestone", state.active_player.id
    elif state.pending_skill is not None:
        kind, owner = "skill", state.active_player.id
    elif state.in_close_phase:
        kind = "close"
        owner = next(p.id for p in state.players if p.role_id == "pm")
    else:
        kind, owner = "move", state.active_player.id
    return Decision(kind=kind, owner=owner, actions=tuple(legal_actions(state)))


def observe(state: GameState, player_id: str) -> str:
    """Plain-text view of the state. Deliberately minimal for this build slice."""
    del player_id  # unused for now: all info is public (rules.md sec 5)
    lines = [
        f"Turn {state.turn} (of 50) -- active player: {state.active_player.id} "
        f"({state.active_player.role_id})",
        f"TAM bank: ${state.bank:.2f}B",
        "Portfolio:",
    ]
    for c in state.portfolio:
        card = state.data.concepts[c.card_id]
        lines.append(
            f"  {card.name} [{c.card_id}] -- {c.position.quadrant_id} "
            f"offset {c.position.offset} -- tokens D{c.tokens.D} V{c.tokens.V} F{c.tokens.F}"
        )
    lines.append(
        "Players: "
        + ", ".join(f"{p.id} ({p.role_id}, skill={p.skill_id or 'none'})" for p in state.players)
    )
    if state.pending_cross is not None:
        lines.append(f"Pending: cross-milestone decision for '{state.pending_cross.concept_id}'")
    elif state.pending_skill is not None:
        skill = state.data.skills[state.pending_skill]
        lines.append(
            f"Pending: {state.active_player.id} drew '{skill.name}', "
            f"not eligible ({state.active_player.role_id}) -- discard or give it away"
        )
    elif state.in_close_phase:
        deck = state.concept_deck
        lines.append(
            f"Close phase (PM decides): remove/draw Concepts or end_close -- "
            f"concept deck has {len(deck.draw_pile)} in draw pile, "
            f"{len(deck.discard_pile)} in discard"
        )
    elif state.pending_roll is not None:
        lines.append(f"Rolled: {state.pending_roll}")
    outcome = is_over(state)
    if outcome is not None:
        lines.append(f"GAME OVER: {outcome.result.upper()} -- {outcome.reason}")
    return "\n".join(lines)
