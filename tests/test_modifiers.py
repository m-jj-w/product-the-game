"""Unit tests for engine/modifiers.py: required_dvf, qualifies, compute_skill_buffs."""

import random

from engine.modifiers import compute_skill_buffs, qualifies, required_dvf
from engine.schema import Concept
from engine.state import BoardPosition, ConceptInstance, DVFTokens, GameState, Player
from tests.fixtures import make_board, make_game_data

BOARD = make_board()
DISCOVERY = next(q for q in BOARD.quadrants if q.id == "discovery")
NPD = next(q for q in BOARD.quadrants if q.id == "npd")
DATA = make_game_data()


def _concept(modifiers: list[dict]) -> Concept:
    return Concept(
        id="c",
        name="C",
        tam=1.0,
        medium=["digital"],
        categories=["product"],
        modifiers=modifiers,
    )


def test_no_modifiers_uses_base_requirement() -> None:
    req = required_dvf(_concept([]), DISCOVERY)
    assert (req.D, req.V, req.F) == (3, 2, 1)


def test_multiply_applies_before_add() -> None:
    # Base D3 V2 F1. multiply all x2, then add +1 D: (3*2)+1=7, not (3+1)*2=8.
    concept = _concept(
        [
            {"type": "modify_requirement", "dim": "all", "op": "multiply", "value": 2},
            {"type": "modify_requirement", "dim": "D", "op": "add", "value": 1},
        ]
    )
    req = required_dvf(concept, DISCOVERY)
    assert (req.D, req.V, req.F) == (7, 4, 2)


def test_order_in_yaml_list_does_not_matter() -> None:
    concept = _concept(
        [
            {"type": "modify_requirement", "dim": "D", "op": "add", "value": 1},
            {"type": "modify_requirement", "dim": "all", "op": "multiply", "value": 2},
        ]
    )
    req = required_dvf(concept, DISCOVERY)
    assert (req.D, req.V, req.F) == (7, 4, 2)


def test_quadrant_scoped_modifier_only_applies_there() -> None:
    concept = _concept(
        [{"type": "modify_requirement", "dim": "D", "op": "add", "value": 5, "quadrant": "npd"}]
    )
    assert required_dvf(concept, DISCOVERY).D == 3
    assert required_dvf(concept, NPD).D == 2 + 5


def test_qualifies_uses_tokens_plus_skill_buffs() -> None:
    concept = _concept([])
    instance = ConceptInstance(
        card_id="c",
        position=BoardPosition("discovery", 1),
        tokens=DVFTokens(D=2, V=2, F=1),
    )
    assert not qualifies(instance, concept, DISCOVERY)  # D short by 1
    assert qualifies(instance, concept, DISCOVERY, skill_buffs=DVFTokens(D=1))


def _state_with_players(players: list[Player]) -> GameState:
    return GameState(
        data=DATA,
        turn=0,
        active_player_index=0,
        turn_owner_index=0,
        players=tuple(players),
        portfolio=(),
        bank=0.0,
        rng_state=random.Random(0).getstate(),
    )


class TestComputeSkillBuffs:
    def test_no_skills_held_gives_zero(self) -> None:
        state = _state_with_players([Player(id="p1", role_id="pm")])
        card = Concept(id="c", name="C", tam=1.0, medium=["digital"], categories=["product"])
        assert compute_skill_buffs(state, card) == DVFTokens()

    def test_filtered_buff_only_matches_the_right_concepts(self) -> None:
        # pm_digital_buff (fixtures.make_skills): +2 V to digital Concepts only.
        state = _state_with_players([Player(id="p1", role_id="pm", skill_id="pm_digital_buff")])
        digital = Concept(id="d", name="D", tam=1.0, medium=["digital"], categories=["product"])
        physical = Concept(id="p", name="P", tam=1.0, medium=["physical"], categories=["product"])
        assert compute_skill_buffs(state, digital) == DVFTokens(V=2)
        assert compute_skill_buffs(state, physical) == DVFTokens()

    def test_filtered_buff_matches_a_concept_with_multiple_mediums(self) -> None:
        # pm_digital_buff filters on medium=digital; a Concept that's both
        # physical and digital should still match (rules.md: a Concept can
        # be physical AND/OR digital).
        state = _state_with_players([Player(id="p1", role_id="pm", skill_id="pm_digital_buff")])
        both = Concept(
            id="b", name="B", tam=1.0, medium=["physical", "digital"], categories=["product"]
        )
        assert compute_skill_buffs(state, both) == DVFTokens(V=2)

    def test_unfiltered_buff_matches_every_concept(self) -> None:
        # all_roles_buff: +1 F, no filter.
        state = _state_with_players([Player(id="p1", role_id="pm", skill_id="all_roles_buff")])
        card = Concept(id="c", name="C", tam=1.0, medium=["physical"], categories=["service"])
        assert compute_skill_buffs(state, card) == DVFTokens(F=1)

    def test_buffs_stack_across_players(self) -> None:
        state = _state_with_players(
            [
                Player(id="p1", role_id="designer", skill_id="designer_buff"),  # +1 D
                Player(id="p2", role_id="pm", skill_id="all_roles_buff"),  # +1 F
            ]
        )
        card = Concept(id="c", name="C", tam=1.0, medium=["digital"], categories=["product"])
        assert compute_skill_buffs(state, card) == DVFTokens(D=1, F=1)

    def test_special_skill_contributes_no_buff(self) -> None:
        state = _state_with_players([Player(id="p1", role_id="pm", skill_id="agile_methods")])
        card = Concept(id="c", name="C", tam=1.0, medium=["digital"], categories=["product"])
        assert compute_skill_buffs(state, card) == DVFTokens()
