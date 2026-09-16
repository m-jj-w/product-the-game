"""End-to-end tests for engine/engine.py: new_game() setup."""

import random
from pathlib import Path

import pytest

from engine.engine import NewGameConfig, current_decision, new_game
from engine.schema import load_game_data
from engine.state import BoardPosition, ConceptInstance, GameState, Player
from tests.fixtures import make_game_data

REAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestNewGameSetup:
    def test_roles_assigned_pm_present_no_duplicates(self) -> None:
        state = new_game(NewGameConfig(data=make_game_data(), player_ids=["a", "b", "c"]), seed=1)
        role_ids = [p.role_id for p in state.players]
        assert "pm" in role_ids
        assert len(role_ids) == len(set(role_ids))
        assert len(state.players) == 3

    def test_five_distinct_starting_concepts_at_entry_gateway(self) -> None:
        data = make_game_data()
        state = new_game(NewGameConfig(data=data, player_ids=["a", "b"]), seed=1)
        assert len(state.portfolio) == 5
        card_ids = {c.card_id for c in state.portfolio}
        assert len(card_ids) == 5

        entry_id = min(data.board.quadrants, key=lambda q: q.order).id
        for c in state.portfolio:
            assert c.position == BoardPosition(entry_id, 0)
            assert c.tokens.D == c.tokens.V == c.tokens.F == 0

    def test_pending_roll_set_for_first_turn(self) -> None:
        state = new_game(NewGameConfig(data=make_game_data(), player_ids=["a"]), seed=1)
        assert state.pending_roll is not None
        assert 1 <= state.pending_roll <= 6

    def test_pm_takes_first_turn(self) -> None:
        state = new_game(NewGameConfig(data=make_game_data(), player_ids=["a", "b", "c"]), seed=1)
        assert state.active_player.role_id == "pm"

    def test_too_few_concepts_raises(self) -> None:
        data = make_game_data(concept_count=3)
        with pytest.raises(ValueError, match="concepts"):
            new_game(NewGameConfig(data=data, player_ids=["a"]), seed=1)

    def test_too_many_players_raises(self) -> None:
        with pytest.raises(ValueError, match="1-5"):
            new_game(
                NewGameConfig(data=make_game_data(), player_ids=["a", "b", "c", "d", "e", "f"]),
                seed=1,
            )

    def test_real_data_dir_currently_lacks_enough_concepts(self) -> None:
        """Documents a known content gap (rules.md sec 12), not an engine bug."""
        data = load_game_data(REAL_DATA_DIR)
        with pytest.raises(ValueError, match="concepts"):
            new_game(NewGameConfig(data=data, player_ids=["a"]), seed=1)

    def test_builds_all_twelve_dvf_sub_decks(self) -> None:
        data = make_game_data()
        state = new_game(NewGameConfig(data=data, player_ids=["a"]), seed=1)
        assert len(state.dvf_sub_decks) == 12
        for quadrant_id in ("discovery", "npd", "scaling", "market_maturity"):
            for dim in ("D", "V", "F"):
                deck = state.dvf_sub_decks[(quadrant_id, dim)]
                assert len(deck.draw_pile) == 2  # fixtures.make_dvf_decks' cards_per_dim default
                assert deck.discard_pile == ()

    def test_concept_deck_holds_leftover_concepts(self) -> None:
        data = make_game_data(concept_count=7)
        state = new_game(NewGameConfig(data=data, player_ids=["a"]), seed=1)
        assert len(state.portfolio) == 5
        assert len(state.concept_deck.draw_pile) == 2
        assert state.concept_deck.discard_pile == ()

        portfolio_ids = {c.card_id for c in state.portfolio}
        deck_ids = set(state.concept_deck.draw_pile)
        assert portfolio_ids.isdisjoint(deck_ids)
        assert portfolio_ids | deck_ids == set(data.concepts)


class TestClosePhaseDecisionOwnership:
    def test_close_decision_is_owned_by_pm_even_when_not_active_player(self) -> None:
        data = make_game_data()
        players = (
            Player(id="alice", role_id="designer"),
            Player(id="bob", role_id="pm"),
        )
        state = GameState(
            data=data,
            turn=0,
            active_player_index=0,  # alice is the active player this turn...
            turn_owner_index=0,
            players=players,
            portfolio=(
                ConceptInstance(card_id="concept_0", position=BoardPosition("discovery", 0)),
            ),
            bank=0.0,
            rng_state=random.Random(0).getstate(),
            in_close_phase=True,
        )
        decision = current_decision(state)
        assert decision is not None
        assert decision.kind == "close"
        assert decision.owner == "bob"  # ...but Close phase decisions belong to the PM
