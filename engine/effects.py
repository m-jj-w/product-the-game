"""Effect primitive registry.

Executes a single `Effect` (engine/schema.py) against a target Concept in
game state. Only primitives actually used by data today are wired up here;
anything else raises `NotImplementedError` rather than silently no-op'ing
— buffs, remove/draw/move-concept, role_swap, role_conditional, and
special handlers arrive with the Portfolio, Skills, and Chance steps.
"""

from __future__ import annotations

import dataclasses

from engine.modifiers import filter_matches
from engine.schema import AddTokensEffect, Effect
from engine.state import DVFTokens, GameState, get_concept, with_concept


def apply_effects(state: GameState, concept_id: str, effects: list[Effect]) -> GameState:
    for effect in effects:
        state = apply_effect(state, concept_id, effect)
    return state


def apply_effect(state: GameState, concept_id: str, effect: Effect) -> GameState:
    if isinstance(effect, AddTokensEffect):
        return _apply_add_tokens(state, concept_id, effect)
    raise NotImplementedError(f"effect type '{effect.type}' is not wired into the engine yet")


def _apply_add_tokens(state: GameState, concept_id: str, effect: AddTokensEffect) -> GameState:
    instance = get_concept(state, concept_id)
    card = state.data.concepts[instance.card_id]
    if not filter_matches(effect.filter, card):
        return state  # card is still drawn/discarded as normal -- just no effect here
    delta = DVFTokens(**{effect.dim: effect.n})
    new_instance = dataclasses.replace(instance, tokens=instance.tokens + delta)
    return with_concept(state, new_instance)
