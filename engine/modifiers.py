"""Milestone requirement calculation.

CLAUDE.md's formula, applied in two passes rather than left-to-right over
the modifier list:

    required = (base[quadrant][dim] x concept_multipliers) + concept_additions
    have     = concept_tokens[dim] + sum(applicable Skill buffs)
    qualifies = have >= required for all of D, V, F
"""

from __future__ import annotations

from engine.schema import Concept, ConceptFilter, ModifyRequirementEffect, Quadrant
from engine.state import ConceptInstance, DVFTokens, GameState

_DIMS = ("D", "V", "F")
_ZERO_TOKENS = DVFTokens()


def _applicable(mod: ModifyRequirementEffect, dim: str, quadrant: Quadrant) -> bool:
    if mod.dim not in (dim, "all"):
        return False
    return mod.quadrant is None or mod.quadrant == quadrant.id


def required_dvf(concept: Concept, quadrant: Quadrant) -> DVFTokens:
    base = quadrant.milestone.requirement
    result: dict[str, float] = {"D": base.D, "V": base.V, "F": base.F}

    for dim in _DIMS:
        multiplier = 1.0
        for mod in concept.modifiers:
            if (
                mod.type == "modify_requirement"
                and mod.op == "multiply"
                and _applicable(mod, dim, quadrant)
            ):
                multiplier *= mod.value
        result[dim] *= multiplier

    for dim in _DIMS:
        addition = 0.0
        for mod in concept.modifiers:
            if (
                mod.type == "modify_requirement"
                and mod.op == "add"
                and _applicable(mod, dim, quadrant)
            ):
                addition += mod.value
        result[dim] += addition

    return DVFTokens(D=round(result["D"]), V=round(result["V"]), F=round(result["F"]))


def qualifies(
    instance: ConceptInstance,
    card: Concept,
    quadrant: Quadrant,
    skill_buffs: DVFTokens = _ZERO_TOKENS,
) -> bool:
    required = required_dvf(card, quadrant)
    have = instance.tokens + skill_buffs
    return have.D >= required.D and have.V >= required.V and have.F >= required.F


def _filter_matches(concept_filter: ConceptFilter | None, card: Concept) -> bool:
    if concept_filter is None:
        return True
    if concept_filter.medium is not None and concept_filter.medium != card.medium:
        return False
    if concept_filter.category is not None and concept_filter.category not in card.categories:
        return False
    return True


def compute_skill_buffs(state: GameState, card: Concept) -> DVFTokens:
    """Sum every player's held Skill's `buff` effects that match `card`.

    rules.md sec 10: every buff from every player's Skill applies to all
    qualifying Concepts, and all buffs stack.
    """
    total = DVFTokens()
    for player in state.players:
        if player.skill_id is None:
            continue
        skill = state.data.skills[player.skill_id]
        for effect in skill.effects:
            if effect.type == "buff" and _filter_matches(effect.filter, card):
                total = total + DVFTokens(**{effect.dim: effect.n})
    return total
