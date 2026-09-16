"""Immutable game state.

`GameState` and everything it's built from are frozen dataclasses. `apply()`
(in rules.py) never mutates a state in place — it always returns a new one.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from engine.schema import GameData


@dataclass(frozen=True)
class DVFTokens:
    """A Concept's own D/V/F counts, or a buff/requirement shaped the same way.

    No floor or ceiling — these can go negative (debt).
    """

    D: int = 0
    V: int = 0
    F: int = 0

    def __add__(self, other: DVFTokens) -> DVFTokens:
        return DVFTokens(self.D + other.D, self.V + other.V, self.F + other.F)


@dataclass(frozen=True)
class BoardPosition:
    """A loop is 16 slots: offset 0 is the Gateway, 1-15 index Quadrant.spaces."""

    quadrant_id: str
    offset: int


@dataclass(frozen=True)
class ConceptInstance:
    """A Concept card currently in the Portfolio.

    `card_id` (a key into `GameData.concepts`) doubles as this instance's
    identifier: Concepts are drawn without replacement, so no two active
    instances share a card_id, and a Finished Concept never returns.
    """

    card_id: str
    position: BoardPosition
    tokens: DVFTokens = field(default_factory=DVFTokens)


@dataclass(frozen=True)
class Player:
    id: str
    role_id: str


@dataclass(frozen=True)
class PendingCross:
    """A qualifying Concept is awaiting an explicit cross-or-not decision."""

    concept_id: str
    same_quadrant_offset: int
    next_quadrant_id: str | None  # None means the milestone leads to Finish


@dataclass(frozen=True)
class Deck:
    """A draw pile plus a discard pile. Cards move straight to discard when
    drawn; the next draw after the pile empties reshuffles the discard.
    Used both for the per-(quadrant, dim) DVF sub-decks and the single
    Concept deck."""

    draw_pile: tuple[str, ...]
    discard_pile: tuple[str, ...] = ()


@dataclass(frozen=True)
class GameState:
    data: GameData
    turn: int
    active_player_index: int
    players: tuple[Player, ...]
    portfolio: tuple[ConceptInstance, ...]
    bank: float
    rng_state: tuple
    dvf_sub_decks: dict[tuple[str, str], Deck] = field(default_factory=dict)
    concept_deck: Deck = field(default_factory=lambda: Deck(draw_pile=()))
    in_close_phase: bool = False
    pending_roll: int | None = None
    pending_cross: PendingCross | None = None

    @property
    def active_player(self) -> Player:
        return self.players[self.active_player_index]


def get_concept(state: GameState, concept_id: str) -> ConceptInstance:
    for c in state.portfolio:
        if c.card_id == concept_id:
            return c
    raise KeyError(f"no active concept '{concept_id}'")


def with_concept(state: GameState, new_instance: ConceptInstance) -> GameState:
    new_portfolio = tuple(
        new_instance if c.card_id == new_instance.card_id else c for c in state.portfolio
    )
    return dataclasses.replace(state, portfolio=new_portfolio)


def entry_quadrant_id(data: GameData) -> str:
    """New Concepts always enter at the lowest-order quadrant (Discovery, rules.md sec 4)."""
    return min(data.board.quadrants, key=lambda q: q.order).id
