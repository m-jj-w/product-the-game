"""Unit tests for engine/effects.py: the effect primitive registry."""

import random

import pytest

from engine.effects import apply_effect, apply_effects
from engine.schema import EffectAdapter
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


def test_unwired_effect_type_raises_not_implemented() -> None:
    state = _state()
    effect = EffectAdapter.validate_python({"type": "remove_concept", "chooser": "team"})
    with pytest.raises(NotImplementedError, match="remove_concept"):
        apply_effect(state, "concept_0", effect)
