"""Pydantic models for every data/*.yaml file, and the loader that validates them.

No engine/game logic lives here — only the shape of the data and the checks
needed to catch a bad card at load time instead of at runtime.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

Dim = Literal["D", "V", "F"]
DimOrAll = Literal["D", "V", "F", "all"]
Medium = Literal["digital", "physical"]
Category = Literal["product", "service", "experience"]
SpaceType = Literal["D", "V", "F", "skills", "chance"]

KNOWN_SPECIAL_HANDLERS = {"agile_methods", "scrum_master"}


class SchemaError(Exception):
    """Raised when a data file fails to parse or a cross-file reference is bad."""


# --- shared value types -----------------------------------------------------


class ConceptFilter(BaseModel):
    model_config = {"extra": "forbid"}

    medium: Medium | None = None
    category: Category | None = None


# --- effect primitives -------------------------------------------------------


class AddTokensEffect(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["add_tokens"] = "add_tokens"
    dim: Dim
    n: int


class ModifyRequirementEffect(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["modify_requirement"] = "modify_requirement"
    dim: DimOrAll
    op: Literal["add", "multiply"]
    value: float
    quadrant: str | None = None


class BuffEffect(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["buff"] = "buff"
    dim: Dim
    n: int
    filter: ConceptFilter | None = None


class RemoveConceptEffect(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["remove_concept"] = "remove_concept"
    chooser: Literal["team"] = "team"


class DrawConceptEffect(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["draw_concept"] = "draw_concept"
    n: int = 1


class MoveConceptEffect(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["move_concept"] = "move_concept"
    n: int | None = None
    to: str | None = None

    @field_validator("to")
    @classmethod
    def _exactly_one_target(cls, to: str | None, info) -> str | None:
        n = info.data.get("n")
        if (n is None) == (to is None):
            raise ValueError("move_concept needs exactly one of 'n' or 'to'")
        return to


class RoleSwapEffect(BaseModel):
    """See rules/open-questions.md #5 — shape is provisional, no example card yet."""

    model_config = {"extra": "forbid"}

    type: Literal["role_swap"] = "role_swap"
    chooser: Literal["team"] = "team"


class RoleConditionalEffect(BaseModel):
    """For Chance cards that affect roles differently."""

    model_config = {"extra": "forbid"}

    type: Literal["role_conditional"] = "role_conditional"
    by_role: dict[str, list[AnyEffect]]


class SpecialEffect(BaseModel):
    """Registry reference, e.g. Agile Methods, Scrum Master.

    Accepts the shorthand `special: agile_methods` in YAML (normalized by
    `_normalize_effect` below) as well as the explicit
    `{type: special, handler: agile_methods}` form.
    """

    model_config = {"extra": "forbid"}

    type: Literal["special"] = "special"
    handler: str

    @field_validator("handler")
    @classmethod
    def _known_handler(cls, handler: str) -> str:
        if handler not in KNOWN_SPECIAL_HANDLERS:
            raise ValueError(
                f"unknown special handler '{handler}'; known handlers: "
                f"{sorted(KNOWN_SPECIAL_HANDLERS)}"
            )
        return handler


Effect = (
    AddTokensEffect
    | ModifyRequirementEffect
    | BuffEffect
    | RemoveConceptEffect
    | DrawConceptEffect
    | MoveConceptEffect
    | RoleSwapEffect
    | RoleConditionalEffect
    | SpecialEffect
)


AnyEffect = Annotated[Effect, Field(discriminator="type")]

RoleConditionalEffect.model_rebuild()

EffectAdapter: TypeAdapter[Effect] = TypeAdapter(AnyEffect)


def _normalize_specials(value: object) -> object:
    """Recursively expand the `special: <handler>` YAML shorthand from CLAUDE.md.

    Pydantic's discriminated-union tag lookup runs before any BeforeValidator
    attached to the union field can rewrite the raw dict, so this shorthand
    has to be expanded in plain Python against the raw YAML tree before it
    ever reaches a model.
    """
    if isinstance(value, dict):
        if set(value) == {"special"}:
            return {"type": "special", "handler": value["special"]}
        return {k: _normalize_specials(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_specials(v) for v in value]
    return value


def parse_effect(raw: dict) -> Effect:
    """Validate a single effect dict, expanding the `special:` shorthand first."""
    return EffectAdapter.validate_python(_normalize_specials(raw))


# --- roles --------------------------------------------------------------


class Role(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    flavor: str | None = None


class RolesFile(BaseModel):
    model_config = {"extra": "forbid"}

    roles: list[Role]


# --- skills ---------------------------------------------------------------


class Skill(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    flavor: str | None = None
    eligible_roles: list[str] = Field(min_length=1)
    effects: list[AnyEffect]


class SkillsFile(BaseModel):
    model_config = {"extra": "forbid"}

    skills: list[Skill]


# --- concepts ---------------------------------------------------------------


class Concept(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    flavor: str | None = None
    tam: float = Field(gt=0)
    medium: Medium
    categories: list[Category] = Field(min_length=1)
    modifiers: list[AnyEffect] = Field(default_factory=list)

    @field_validator("categories")
    @classmethod
    def _unique_categories(cls, categories: list[Category]) -> list[Category]:
        if len(set(categories)) != len(categories):
            raise ValueError("categories must be unique")
        return categories


class ConceptsFile(BaseModel):
    model_config = {"extra": "forbid"}

    concepts: list[Concept]


# --- chance -------------------------------------------------------------


class ChanceCard(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    flavor: str | None = None
    effects: list[AnyEffect]


class ChanceFile(BaseModel):
    model_config = {"extra": "forbid"}

    chance_cards: list[ChanceCard]


# --- DVF ------------------------------------------------------------------


class DvfCard(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    dim: Dim
    flavor: str | None = None
    effects: list[AnyEffect]


class DvfDeck(BaseModel):
    model_config = {"extra": "forbid"}

    quadrant: str
    cards: list[DvfCard] = Field(default_factory=list)


# --- board ------------------------------------------------------------------


class DVFRequirement(BaseModel):
    model_config = {"extra": "forbid"}

    D: int = Field(ge=0)
    V: int = Field(ge=0)
    F: int = Field(ge=0)


class Milestone(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    requirement: DVFRequirement
    leads_to: str


_SPACE_TYPES: tuple[SpaceType, ...] = ("D", "V", "F", "skills", "chance")


class Quadrant(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    name: str
    order: int
    milestone: Milestone
    spaces: list[SpaceType]

    @field_validator("spaces")
    @classmethod
    def _fifteen_spaces_three_of_each(cls, spaces: list[SpaceType]) -> list[SpaceType]:
        if len(spaces) != 15:
            raise ValueError(f"spaces must have exactly 15 entries, got {len(spaces)}")
        counts = Counter(spaces)
        for space_type in _SPACE_TYPES:
            if counts.get(space_type, 0) != 3:
                raise ValueError(
                    f"spaces must have exactly 3 of type '{space_type}', "
                    f"got {counts.get(space_type, 0)}"
                )
        return spaces


class Board(BaseModel):
    model_config = {"extra": "forbid"}

    quadrants: list[Quadrant]

    @field_validator("quadrants")
    @classmethod
    def _four_quadrants_unique_orders(cls, quadrants: list[Quadrant]) -> list[Quadrant]:
        if len(quadrants) != 4:
            raise ValueError(f"board must have exactly 4 quadrants, got {len(quadrants)}")
        orders = sorted(q.order for q in quadrants)
        if orders != [1, 2, 3, 4]:
            raise ValueError(f"quadrant orders must be exactly 1-4, got {orders}")
        return quadrants


# --- loader -------------------------------------------------------------


@dataclass(frozen=True)
class GameData:
    roles: dict[str, Role]
    skills: dict[str, Skill]
    concepts: dict[str, Concept]
    chance_cards: dict[str, ChanceCard]
    dvf_decks: dict[str, DvfDeck] = field(default_factory=dict)
    board: Board | None = None


def _load_yaml(path: Path) -> object:
    if not path.exists():
        raise SchemaError(f"{path}: file not found")
    with path.open() as f:
        return yaml.safe_load(f)


def _parse(model: type[BaseModel], path: Path) -> BaseModel:
    raw = _normalize_specials(_load_yaml(path))
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise SchemaError(f"{path}: {exc}") from exc


def _check_effects(effects: list[Effect], role_ids: set[str], context: str) -> None:
    for effect in effects:
        if isinstance(effect, RoleConditionalEffect):
            for role_id, nested in effect.by_role.items():
                if role_id not in role_ids:
                    raise SchemaError(
                        f"{context}: role_conditional references unknown role '{role_id}'"
                    )
                _check_effects(nested, role_ids, context)


def _validate_cross_references(data: GameData) -> None:
    role_ids = set(data.roles)
    assert data.board is not None
    quadrant_ids = {q.id for q in data.board.quadrants}

    for skill in data.skills.values():
        for role_id in skill.eligible_roles:
            if role_id not in role_ids:
                raise SchemaError(f"skill '{skill.id}' references unknown role '{role_id}'")
        _check_effects(skill.effects, role_ids, f"skill '{skill.id}'")

    for concept in data.concepts.values():
        _check_effects(concept.modifiers, role_ids, f"concept '{concept.id}'")

    for card in data.chance_cards.values():
        _check_effects(card.effects, role_ids, f"chance card '{card.id}'")

    for deck in data.dvf_decks.values():
        if deck.quadrant not in quadrant_ids:
            raise SchemaError(f"dvf deck references unknown quadrant '{deck.quadrant}'")
        for card in deck.cards:
            _check_effects(card.effects, role_ids, f"dvf card '{card.id}'")

    for quadrant in data.board.quadrants:
        target = quadrant.milestone.leads_to
        if target != "finish" and target not in quadrant_ids:
            raise SchemaError(
                f"quadrant '{quadrant.id}' milestone leads_to unknown quadrant '{target}'"
            )


def load_game_data(data_dir: Path | str) -> GameData:
    """Load and cross-validate every data/*.yaml file under `data_dir`."""
    data_dir = Path(data_dir)

    roles_file = _parse(RolesFile, data_dir / "roles.yaml")
    skills_file = _parse(SkillsFile, data_dir / "skills.yaml")
    concepts_file = _parse(ConceptsFile, data_dir / "concepts.yaml")
    chance_file = _parse(ChanceFile, data_dir / "chance.yaml")
    board = _parse(Board, data_dir / "board.yaml")

    dvf_decks: dict[str, DvfDeck] = {}
    for path in sorted((data_dir / "dvf").glob("*.yaml")):
        deck = _parse(DvfDeck, path)
        dvf_decks[deck.quadrant] = deck

    data = GameData(
        roles={r.id: r for r in roles_file.roles},
        skills={s.id: s for s in skills_file.skills},
        concepts={c.id: c for c in concepts_file.concepts},
        chance_cards={c.id: c for c in chance_file.chance_cards},
        dvf_decks=dvf_decks,
        board=board,
    )
    _validate_cross_references(data)
    return data
