"""Milestone requirement calculation.

CLAUDE.md's formula, applied in two passes rather than left-to-right over
the modifier list:

    required = (base[quadrant][dim] x concept_multipliers) + concept_additions
    have     = concept_tokens[dim] + sum(applicable Skill buffs)
    qualifies = have >= required for all of D, V, F
"""

from __future__ import annotations

from engine.schema import Concept, ModifyRequirementEffect, Quadrant
from engine.state import ConceptInstance, DVFTokens

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
