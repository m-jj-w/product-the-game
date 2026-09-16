"""Unit tests for engine/modifiers.py: required_dvf and qualifies."""

from engine.modifiers import qualifies, required_dvf
from engine.schema import Concept
from engine.state import BoardPosition, ConceptInstance, DVFTokens
from tests.fixtures import make_board

BOARD = make_board()
DISCOVERY = next(q for q in BOARD.quadrants if q.id == "discovery")
NPD = next(q for q in BOARD.quadrants if q.id == "npd")


def _concept(modifiers: list[dict]) -> Concept:
    return Concept(
        id="c",
        name="C",
        tam=1.0,
        medium="digital",
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
