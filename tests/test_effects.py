"""Unit tests for engine/effects.py: the effect primitive registry."""

import dataclasses
import random

import pytest

from engine.effects import apply_effect, apply_effects
from engine.schema import Concept, EffectAdapter
from engine.state import BoardPosition, ConceptInstance, DVFTokens, GameState, Player
from tests.fixtures import make_game_data

DATA = make_game_data()


def _state(tokens: DVFTokens | None = None) -> GameState:
    concept = ConceptInstance(
        card_id="concept_0",
        position=BoardPosition("discovery", 1),
        tokens=tokens or DVFTokens(),
    )
    return GameState(
        data=DATA,
        turn=0,
        active_player_index=0,
        turn_owner_index=0,
        players=(Player(id="p1", role_id="pm"),),
        portfolio=(concept,),
        bank=0.0,
        rng_state=random.Random(0).getstate(),
    )


def test_add_tokens_effect_adds_to_the_right_dim() -> None:
    state = _state(tokens=DVFTokens(D=1))
    effect = EffectAdapter.validate_python({"type": "add_tokens", "dim": "V", "n": 3})
    result = apply_effect(state, "concept_0", effect)
    assert result.portfolio[0].tokens == DVFTokens(D=1, V=3, F=0)


def test_add_tokens_can_go_negative() -> None:
    state = _state(tokens=DVFTokens(D=2))
    effect = EffectAdapter.validate_python({"type": "add_tokens", "dim": "D", "n": -5})
    result = apply_effect(state, "concept_0", effect)
    assert result.portfolio[0].tokens.D == -3


def test_apply_effects_folds_a_list_in_order() -> None:
    state = _state()
    effects = [
        EffectAdapter.validate_python({"type": "add_tokens", "dim": "D", "n": 1}),
        EffectAdapter.validate_python({"type": "add_tokens", "dim": "D", "n": 2}),
    ]
    result = apply_effects(state, "concept_0", effects)
    assert result.portfolio[0].tokens.D == 3


def test_add_tokens_filter_applies_when_it_matches() -> None:
    # fixtures.make_concepts: concept_0 is medium=["digital"], categories=["product"]
    state = _state()
    effect = EffectAdapter.validate_python(
        {"type": "add_tokens", "dim": "D", "n": 1, "filter": {"medium": "digital"}}
    )
    result = apply_effect(state, "concept_0", effect)
    assert result.portfolio[0].tokens.D == 1


def test_add_tokens_filter_no_ops_when_it_does_not_match() -> None:
    state = _state()
    effect = EffectAdapter.validate_python(
        {"type": "add_tokens", "dim": "D", "n": 1, "filter": {"medium": "physical"}}
    )
    result = apply_effect(state, "concept_0", effect)
    # the card is still "used" (a DVF/Chance card is discarded regardless,
    # handled by the caller) -- this just confirms the target is untouched
    assert result.portfolio[0].tokens.D == 0


def test_add_tokens_filter_by_category_no_match() -> None:
    state = _state()
    effect = EffectAdapter.validate_python(
        {"type": "add_tokens", "dim": "D", "n": 1, "filter": {"category": "service"}}
    )
    result = apply_effect(state, "concept_0", effect)
    assert result.portfolio[0].tokens.D == 0


def test_add_tokens_filter_matches_one_of_several_mediums() -> None:
    # a Concept can be physical AND/OR digital -- a single-medium filter
    # should match if that medium is among the Concept's several.
    both = Concept(
        id="both", name="Both", tam=0.75, medium=["physical", "digital"], categories=["experience"]
    )
    data = dataclasses.replace(DATA, concepts={**DATA.concepts, "both": both})
    concept = ConceptInstance(
        card_id="both", position=BoardPosition("discovery", 1), tokens=DVFTokens()
    )
    state = GameState(
        data=data,
        turn=0,
        active_player_index=0,
        turn_owner_index=0,
        players=(Player(id="p1", role_id="pm"),),
        portfolio=(concept,),
        bank=0.0,
        rng_state=random.Random(0).getstate(),
    )
    effect = EffectAdapter.validate_python(
        {"type": "add_tokens", "dim": "F", "n": 2, "filter": {"medium": "physical"}}
    )
    result = apply_effect(state, "both", effect)
    assert result.portfolio[0].tokens.F == 2


def test_unwired_effect_type_raises_not_implemented() -> None:
    state = _state()
    effect = EffectAdapter.validate_python({"type": "remove_concept", "chooser": "team"})
    with pytest.raises(NotImplementedError, match="remove_concept"):
        apply_effect(state, "concept_0", effect)
