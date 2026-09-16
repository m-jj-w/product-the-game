"""Tests for engine/rules.py: wrap/cross mechanics, win/loss, replay determinism."""

import random

import pytest

from engine.engine import NewGameConfig, new_game
from engine.rules import CrossMilestone, MoveConcept, apply, is_over, legal_actions
from engine.state import BoardPosition, ConceptInstance, DVFTokens, GameState, PendingCross, Player
from tests.fixtures import make_game_data

DATA = make_game_data()


def _concept(card_id="concept_0", quadrant="discovery", offset=0, tokens=None):
    return ConceptInstance(
        card_id=card_id,
        position=BoardPosition(quadrant, offset),
        tokens=tokens or DVFTokens(),
    )


def _state(
    *,
    portfolio,
    turn=0,
    active_player_index=0,
    bank=0.0,
    pending_roll=None,
    pending_cross=None,
    rng_seed=0,
) -> GameState:
    return GameState(
        data=DATA,
        turn=turn,
        active_player_index=active_player_index,
        players=(Player(id="p1", role_id="pm"), Player(id="p2", role_id="designer")),
        portfolio=tuple(portfolio),
        bank=bank,
        rng_state=random.Random(rng_seed).getstate(),
        pending_roll=pending_roll,
        pending_cross=pending_cross,
    )


class TestWrapping:
    def test_forward_wrap_when_not_qualified(self) -> None:
        state = _state(portfolio=[_concept(offset=12)], pending_roll=6)
        result = apply(state, MoveConcept("concept_0", "forward"))
        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", (12 + 6) % 16)
        assert result.pending_cross is None
        assert result.pending_roll is not None
        assert result.turn == 1
        assert result.active_player_index == 1

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
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id="npd"),
        )
        result = apply(state, CrossMilestone("concept_0", cross=False))
        c = result.portfolio[0]
        assert c.position == BoardPosition("discovery", 2)
        assert c.tokens == DVFTokens(D=3, V=2, F=1)
        assert result.pending_cross is None
        assert result.turn == 1

    def test_accept_cross_moves_to_next_gateway_and_resets_tokens(self) -> None:
        state = _state(
            portfolio=[_concept(offset=12, tokens=DVFTokens(D=3, V=2, F=1))],
            pending_cross=PendingCross("concept_0", same_quadrant_offset=2, next_quadrant_id="npd"),
        )
        result = apply(state, CrossMilestone("concept_0", cross=True))
        c = result.portfolio[0]
        assert c.position == BoardPosition("npd", 0)
        assert c.tokens == DVFTokens()
        assert result.turn == 1

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

    def test_loss_when_fifty_turns_elapse(self) -> None:
        state = _state(portfolio=[_concept(offset=0)], turn=49, pending_roll=3)
        result = apply(state, MoveConcept("concept_0", "forward"))
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
