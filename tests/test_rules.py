"""Tests for engine/rules.py: wrap/cross mechanics, win/loss, replay determinism."""

import random

import pytest

from engine.engine import NewGameConfig, new_game
from engine.rules import (
    ChanceRemoveConcept,
    CrossMilestone,
    DiscardSkill,
    DrawConcept,
    EndClose,
    GiveSkill,
    MoveConcept,
    RemoveConcept,
    apply,
    is_over,
    legal_actions,
)
from engine.state import (
    BoardPosition,
    ConceptInstance,
    Deck,
    DVFTokens,
    GameState,
    PendingCross,
    Player,
)
from tests.fixtures import make_game_data

DATA = make_game_data()
# A fully-shuffled, deterministic starting point for every (quadrant, dim)
# sub-deck, reused as the default for hand-built states below so landing on
# a D/V/F space during a test doesn't blow up on a missing sub-deck.
_INITIAL_SUB_DECKS: dict[tuple[str, str], Deck] = new_game(
    NewGameConfig(data=DATA, player_ids=["_fixture"]), seed=0
).dvf_sub_decks


def _concept(card_id="concept_0", quadrant="discovery", offset=0, tokens=None):
    return ConceptInstance(
        card_id=card_id,
        position=BoardPosition(quadrant, offset),
        tokens=tokens or DVFTokens(),
    )


_DEFAULT_PLAYERS = (Player(id="p1", role_id="pm"), Player(id="p2", role_id="designer"))


def _state(
    *,
    portfolio,
    turn=0,
    active_player_index=0,
    turn_owner_index=None,
    players=None,
    bank=0.0,
    pending_roll=None,
    pending_cross=None,
    dvf_sub_decks=None,
    concept_deck=None,
    skill_deck=None,
    chance_deck=None,
    in_close_phase=False,
    agile_bonus_pending=False,
    pending_skill=None,
    pending_chance_removal=False,
    rng_seed=0,
) -> GameState:
    return GameState(
        data=DATA,
        turn=turn,
        active_player_index=active_player_index,
        turn_owner_index=turn_owner_index if turn_owner_index is not None else active_player_index,
        players=players if players is not None else _DEFAULT_PLAYERS,
        portfolio=tuple(portfolio),
        bank=bank,
        rng_state=random.Random(rng_seed).getstate(),
        dvf_sub_decks=dvf_sub_decks if dvf_sub_decks is not None else _INITIAL_SUB_DECKS,
        concept_deck=concept_deck if concept_deck is not None else Deck(draw_pile=()),
        skill_deck=skill_deck if skill_deck is not None else Deck(draw_pile=()),
        chance_deck=chance_deck if chance_deck is not None else Deck(draw_pile=()),
        in_close_phase=in_close_phase,
        agile_bonus_pending=agile_bonus_pending,
        pending_roll=pending_roll,
        pending_cross=pending_cross,
        pending_skill=pending_skill,
        pending_chance_removal=pending_chance_removal,
    )


class TestWrapping:
    def test_forward_wrap_when_not_qualified(self) -> None:
        state = _state(portfolio=[_concept(offset=12)], pending_roll=6)
        result = apply(state, MoveConcept("concept_0", "forward"))
        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", (12 + 6) % 16)
        assert result.pending_cross is None
        # Move+Draw resolved into the Close phase -- the turn doesn't end
        # (and no next die is rolled) until end_close (see TestClosePhase).
        assert result.in_close_phase is True
        assert result.pending_roll is None
        assert result.turn == 0
        assert result.active_player_index == 0

    def test_backward_wrap_never_offers_crossing_even_if_qualified(self) -> None:
        state = _state(
            portfolio=[_concept(offset=3, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_roll=6,
        )
        result = apply(state, MoveConcept("concept_0", "backward"))
        assert result.pending_cross is None
        assert result.portfolio[0].position == BoardPosition("discovery", (3 - 6) % 16)


class TestCrossing:
    def test_qualified_forward_move_offers_cross_decision(self) -> None:
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_roll=6,
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        assert result.pending_cross == PendingCross(
            concept_id="concept_0", same_quadrant_offset=(12 + 6) % 16, next_quadrant_id="npd"
        )
        assert result.pending_roll is None
        assert result.turn == 0  # turn doesn't end until the cross decision resolves

    def test_legal_actions_for_pending_cross(self) -> None:
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id="npd"),
        )
        actions = legal_actions(state)
        assert set(actions) == {
            CrossMilestone("concept_0", True),
            CrossMilestone("concept_0", False),
        }

    def test_decline_cross_wraps_and_keeps_tokens(self) -> None:
        # offset 0 is the Gateway -- guaranteed no draw of any kind, so this
        # test stays focused on crossing-decline semantics rather than DVF
        # or Skill drawing (covered separately in TestDvfDraws/TestSkills).
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_cross=PendingCross("concept_0", same_quadrant_offset=0, next_quadrant_id="npd"),
        )
        result = apply(state, CrossMilestone("concept_0", cross=False))
        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", 0)
        assert c.tokens == DVFTokens(D=3, V=2, F=1)
        assert result.pending_cross is None
        assert result.in_close_phase is True
        assert result.turn == 0

    def test_accept_cross_moves_to_next_gateway_and_resets_tokens(self) -> None:
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id="npd"),
        )
        result = apply(state, CrossMilestone("concept_0", cross=True))
        c = result.portfolio[0]
        assert c.position == BoardPosition("npd", 0)
        assert c.tokens == DVFTokens()
        assert result.in_close_phase is True
        assert result.turn == 0

    def test_finish_removes_concept_and_credits_bank(self) -> None:
        state = _state(
            portfolio=[
                _concept(card_id="concept_0", quadrant="market_maturity", offset=12),
                _concept(card_id="concept_1", quadrant="discovery", offset=1),
            ],
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id=None),
        )
        result = apply(state, CrossMilestone("concept_0", cross=True))
        assert "concept_0" not in {c.card_id for c in result.portfolio}
        assert result.bank == pytest.approx(DATA.concepts["concept_0"].tam)
        # concept_1 is still active and the game isn't over -- Close phase still happens.
        assert result.in_close_phase is True


class TestWinLoss:
    def test_win_when_bank_reaches_threshold(self) -> None:
        state = _state(
            portfolio=[_concept(card_id="concept_0", quadrant="market_maturity", offset=12)],
            bank=0.8,
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id=None),
        )
        result = apply(state, CrossMilestone("concept_0", cross=True))
        outcome = is_over(result)
        assert outcome is not None and outcome.result == "win"
        assert result.pending_roll is None
        assert result.in_close_phase is False  # no Close phase once the game's over
        assert result.turn == state.turn  # frozen: no next turn rolled

    def test_loss_when_last_concept_finishes_under_threshold(self) -> None:
        state = _state(
            portfolio=[_concept(card_id="concept_0", quadrant="market_maturity", offset=12)],
            bank=0.0,
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id=None),
        )
        result = apply(state, CrossMilestone("concept_0", cross=True))
        outcome = is_over(result)
        assert outcome is not None and outcome.result == "loss"
        assert not result.portfolio
        assert result.in_close_phase is False

    def test_loss_when_fifty_turns_elapse(self) -> None:
        state = _state(portfolio=[_concept(offset=0)], turn=49, pending_roll=3)
        state = apply(state, MoveConcept("concept_0", "forward"))
        assert state.in_close_phase is True
        assert state.turn == 49  # still the 49th turn until Close ends

        result = apply(state, EndClose())
        assert result.turn == 50
        outcome = is_over(result)
        assert outcome is not None and outcome.result == "loss"

    def test_apply_after_game_over_raises(self) -> None:
        state = _state(portfolio=[_concept(offset=0)], turn=50, pending_roll=3)
        with pytest.raises(ValueError, match="already over"):
            apply(state, MoveConcept("concept_0", "forward"))

    def test_legal_actions_empty_when_over(self) -> None:
        state = _state(portfolio=[_concept(offset=0)], turn=50, pending_roll=3)
        assert legal_actions(state) == []


class TestReplayDeterminism:
    def test_same_seed_and_actions_give_identical_state(self) -> None:
        config = NewGameConfig(data=DATA, player_ids=["p1", "p2", "p3"])
        s1 = new_game(config, seed=42)
        s2 = new_game(config, seed=42)
        assert s1 == s2

        actions = []
        state1 = s1
        for _ in range(10):
            action = legal_actions(state1)[0]
            actions.append(action)
            state1 = apply(state1, action)

        state2 = s2
        for action in actions:
            state2 = apply(state2, action)

        assert state1 == state2


class TestDvfDraws:
    def test_landing_on_dvf_space_draws_applies_and_discards(self) -> None:
        # offset 1 is a "D" space in the fixture board.
        state = _state(portfolio=[_concept(offset=0)], pending_roll=1)
        result = apply(state, MoveConcept("concept_0", "forward"))

        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", 1)
        assert c.tokens.D == 1  # the drawn card's add_tokens effect

        before = _INITIAL_SUB_DECKS[("discovery", "D")]
        after = result.dvf_sub_decks[("discovery", "D")]
        assert len(after.draw_pile) == len(before.draw_pile) - 1
        assert len(after.discard_pile) == 1

    def test_exact_wrap_to_gateway_never_draws(self) -> None:
        # offset 10 + roll 6 = raw 16 exactly -> wraps to offset 0 (Gateway).
        state = _state(portfolio=[_concept(offset=10)], pending_roll=6)
        result = apply(state, MoveConcept("concept_0", "forward"))

        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", 0)
        assert c.tokens == DVFTokens()
        assert result.dvf_sub_decks == state.dvf_sub_decks

    def test_reshuffle_when_draw_pile_empties(self) -> None:
        depleted = dict(_INITIAL_SUB_DECKS)
        depleted[("discovery", "D")] = Deck(draw_pile=("discovery_D_0",))
        state = _state(portfolio=[_concept(offset=0)], pending_roll=1, dvf_sub_decks=depleted)

        state = apply(state, MoveConcept("concept_0", "forward"))  # empties the draw pile
        after_first = state.dvf_sub_decks[("discovery", "D")]
        assert after_first == Deck(draw_pile=(), discard_pile=("discovery_D_0",))

        # Land on the same D space again, reusing that now-empty-draw-pile deck.
        state2 = _state(
            portfolio=[_concept(offset=0)], pending_roll=1, dvf_sub_decks=state.dvf_sub_decks
        )
        result = apply(state2, MoveConcept("concept_0", "forward"))
        after_second = result.dvf_sub_decks[("discovery", "D")]
        # reshuffled the 1-card discard back into a draw pile and drew it again
        assert after_second == Deck(draw_pile=(), discard_pile=("discovery_D_0",))
        assert result.portfolio[0].tokens.D == 1  # state2's concept started fresh at 0

    def test_drawing_from_empty_subdeck_raises_clear_error(self) -> None:
        empty_decks = dict(_INITIAL_SUB_DECKS)
        empty_decks[("discovery", "D")] = Deck(draw_pile=())  # no cards defined at all
        state = _state(portfolio=[_concept(offset=0)], pending_roll=1, dvf_sub_decks=empty_decks)
        with pytest.raises(ValueError, match="no cards defined"):
            apply(state, MoveConcept("concept_0", "forward"))


class TestClosePhase:
    def _five_concept_portfolio(self):
        return [_concept(card_id=f"concept_{i}", offset=4) for i in range(5)]  # skills space

    def test_remove_blocked_at_minimum(self) -> None:
        state = _state(portfolio=[_concept()], in_close_phase=True)
        assert legal_actions(state) == [EndClose()]  # no RemoveConcept offered
        with pytest.raises(ValueError, match="last active Concept"):
            apply(state, RemoveConcept("concept_0"))

    def test_remove_sends_card_to_discard_and_stays_in_close_phase(self) -> None:
        state = _state(
            portfolio=self._five_concept_portfolio(),
            in_close_phase=True,
            concept_deck=Deck(draw_pile=("concept_5",)),
        )
        result = apply(state, RemoveConcept("concept_0"))
        assert "concept_0" not in {c.card_id for c in result.portfolio}
        assert len(result.portfolio) == 4
        assert result.concept_deck.discard_pile == ("concept_0",)
        assert result.in_close_phase is True  # a single action doesn't end the phase

    def test_removed_concept_redrawn_later_starts_at_zero_tokens(self) -> None:
        state = _state(
            portfolio=self._five_concept_portfolio(),
            in_close_phase=True,
            concept_deck=Deck(draw_pile=()),
        )
        removed = apply(state, RemoveConcept("concept_0"))
        # concept_0 is now the only card in the discard pile; draw it straight back.
        redrawn = apply(removed, DrawConcept())
        new_instance = next(c for c in redrawn.portfolio if c.card_id == "concept_0")
        assert new_instance.tokens == DVFTokens()
        assert new_instance.position == BoardPosition("discovery", 0)

    def test_draw_blocked_at_five(self) -> None:
        state = _state(
            portfolio=self._five_concept_portfolio(),
            in_close_phase=True,
            concept_deck=Deck(draw_pile=("concept_5",)),
        )
        assert DrawConcept() not in legal_actions(state)
        with pytest.raises(ValueError, match="already has 5"):
            apply(state, DrawConcept())

    def test_draw_not_offered_when_deck_is_empty(self) -> None:
        state = _state(portfolio=[_concept()], in_close_phase=True, concept_deck=Deck(draw_pile=()))
        assert DrawConcept() not in legal_actions(state)

    def test_draw_places_new_concept_at_entry_gateway(self) -> None:
        state = _state(
            portfolio=[_concept()], in_close_phase=True, concept_deck=Deck(draw_pile=("concept_9",))
        )
        result = apply(state, DrawConcept())
        assert len(result.portfolio) == 2
        new_instance = next(c for c in result.portfolio if c.card_id == "concept_9")
        assert new_instance.position == BoardPosition("discovery", 0)
        assert new_instance.tokens == DVFTokens()
        assert result.concept_deck.draw_pile == ()

    def test_draw_reshuffles_deck_when_draw_pile_empty(self) -> None:
        state = _state(
            portfolio=[_concept()],
            in_close_phase=True,
            concept_deck=Deck(draw_pile=(), discard_pile=("concept_9",)),
        )
        result = apply(state, DrawConcept())
        assert {c.card_id for c in result.portfolio} == {"concept_0", "concept_9"}
        # drawn into the Portfolio, not discarded -- reshuffle emptied the discard too
        assert result.concept_deck == Deck(draw_pile=(), discard_pile=())

    def test_end_close_rolls_next_die_and_advances_turn_and_player(self) -> None:
        state = _state(portfolio=[_concept()], turn=3, active_player_index=0, in_close_phase=True)
        result = apply(state, EndClose())
        assert result.in_close_phase is False
        assert result.turn == 4
        assert result.active_player_index == 1
        assert result.pending_roll is not None

    def test_actions_outside_close_phase_are_rejected(self) -> None:
        state = _state(portfolio=[_concept()], pending_roll=3)  # not in Close phase
        with pytest.raises(ValueError, match="not in the Close phase"):
            apply(state, EndClose())
        with pytest.raises(ValueError, match="not in the Close phase"):
            apply(state, DrawConcept())


class TestSkills:
    """offset 0 + roll 4 always lands on a 'skills' space (offset 4) in the
    fixture board's [D,V,F,skills,chance]x3 pattern."""

    def test_eligible_skill_auto_taken_replaces_old(self) -> None:
        players = (
            Player(id="p1", role_id="designer", skill_id="all_roles_buff"),
            Player(id="p2", role_id="pm"),
        )
        state = _state(
            portfolio=[_concept(offset=0)],
            players=players,
            active_player_index=0,
            pending_roll=4,
            skill_deck=Deck(draw_pile=("designer_buff",)),
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        assert result.players[0].skill_id == "designer_buff"
        assert result.skill_deck.draw_pile == ()
        assert result.skill_deck.discard_pile == ("all_roles_buff",)  # old skill discarded
        assert result.pending_skill is None
        assert result.in_close_phase is True  # no decision needed, proceeds normally

    def test_ineligible_skill_pauses_with_only_discard_when_nobody_eligible(self) -> None:
        players = (
            Player(id="p1", role_id="engineer"),
            Player(id="p2", role_id="pm"),  # neither eligible for designer_buff
        )
        state = _state(
            portfolio=[_concept(offset=0)],
            players=players,
            active_player_index=0,
            pending_roll=4,
            skill_deck=Deck(draw_pile=("designer_buff",)),
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        assert result.pending_skill == "designer_buff"
        assert result.in_close_phase is False
        assert result.turn == 0
        assert legal_actions(result) == [DiscardSkill()]

    def test_ineligible_skill_offers_give_to_eligible_teammate(self) -> None:
        players = (
            Player(id="p1", role_id="engineer"),
            Player(id="p2", role_id="designer"),  # eligible for designer_buff
        )
        state = _state(
            portfolio=[_concept(offset=0)],
            players=players,
            active_player_index=0,
            pending_roll=4,
            skill_deck=Deck(draw_pile=("designer_buff",)),
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        assert set(legal_actions(result)) == {DiscardSkill(), GiveSkill("p2")}

    def test_give_skill_ends_turn_with_no_close_phase(self) -> None:
        players = (
            Player(id="p1", role_id="engineer"),
            Player(id="p2", role_id="designer"),
        )
        state = _state(
            portfolio=[_concept(offset=0)],
            players=players,
            active_player_index=0,
            turn=2,
            pending_roll=4,
            skill_deck=Deck(draw_pile=("designer_buff",)),
        )
        state = apply(state, MoveConcept("concept_0", "forward"))
        result = apply(state, GiveSkill("p2"))
        assert result.players[1].skill_id == "designer_buff"
        assert result.pending_skill is None
        assert result.in_close_phase is False  # never entered
        assert result.turn == 3  # ended immediately via _end_turn
        assert result.active_player_index == 1

    def test_discard_skill_proceeds_to_close_phase(self) -> None:
        players = (Player(id="p1", role_id="engineer"), Player(id="p2", role_id="pm"))
        state = _state(
            portfolio=[_concept(offset=0)],
            players=players,
            active_player_index=0,
            pending_roll=4,
            skill_deck=Deck(draw_pile=("designer_buff",)),
        )
        state = apply(state, MoveConcept("concept_0", "forward"))
        result = apply(state, DiscardSkill())
        assert result.pending_skill is None
        assert result.skill_deck.discard_pile == ("designer_buff",)
        assert result.in_close_phase is True
        assert result.players[0].skill_id is None  # never took it

    def test_skill_buff_helps_concept_qualify_for_crossing(self) -> None:
        # Discovery requires D3 V2 F1. The Concept has D2 (short by 1).
        # p2's designer_buff (+1 D, unfiltered) closes the gap.
        players = (
            Player(id="p1", role_id="pm"),
            Player(id="p2", role_id="designer", skill_id="designer_buff"),
        )
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=2, V=2, F=1))],
            players=players,
            active_player_index=0,
            pending_roll=6,
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        assert result.pending_cross is not None


class TestChance:
    """offset 0 + roll 5 always lands on a 'chance' space (offset 5)."""

    def test_plain_chance_effect_applies_to_landing_concept(self) -> None:
        state = _state(
            portfolio=[_concept(offset=0)],
            pending_roll=5,
            chance_deck=Deck(draw_pile=("test_bonus",)),
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", 5)
        assert c.tokens.D == 1
        assert result.chance_deck == Deck(draw_pile=(), discard_pile=("test_bonus",))
        assert result.pending_chance_removal is False
        assert result.in_close_phase is True

    def test_removal_chance_pauses_for_team_decision(self) -> None:
        state = _state(
            portfolio=[
                _concept(card_id="concept_0", offset=0),
                _concept(card_id="concept_1", offset=3),
            ],
            pending_roll=5,
            chance_deck=Deck(draw_pile=("test_removal",)),
        )
        result = apply(state, MoveConcept("concept_0", "forward"))
        assert result.pending_chance_removal is True
        assert result.in_close_phase is False
        assert result.turn == 0
        # the card itself is used up immediately, regardless of the pending target choice
        assert result.chance_deck == Deck(draw_pile=(), discard_pile=("test_removal",))
        assert set(legal_actions(result)) == {
            ChanceRemoveConcept("concept_0"),
            ChanceRemoveConcept("concept_1"),
        }

    def test_removal_down_to_zero_ends_game_as_loss_without_close_phase(self) -> None:
        state = _state(portfolio=[_concept(offset=0)], pending_chance_removal=True)
        result = apply(state, ChanceRemoveConcept("concept_0"))
        assert not result.portfolio
        outcome = is_over(result)
        assert outcome is not None and outcome.result == "loss"
        assert result.in_close_phase is False
        assert result.pending_chance_removal is False

    def test_removal_with_others_remaining_proceeds_to_close_phase(self) -> None:
        state = _state(
            portfolio=[
                _concept(card_id="concept_0", offset=0),
                _concept(card_id="concept_1", offset=3),
            ],
            pending_chance_removal=True,
        )
        result = apply(state, ChanceRemoveConcept("concept_0"))
        assert {c.card_id for c in result.portfolio} == {"concept_1"}
        assert result.concept_deck.discard_pile == ("concept_0",)
        assert result.in_close_phase is True
        assert result.pending_chance_removal is False

    def test_drawing_from_empty_chance_deck_raises_clear_error(self) -> None:
        state = _state(
            portfolio=[_concept(offset=0)], pending_roll=5, chance_deck=Deck(draw_pile=())
        )
        with pytest.raises(ValueError, match="no Chance cards defined"):
            apply(state, MoveConcept("concept_0", "forward"))
