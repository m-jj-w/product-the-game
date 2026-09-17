"""Tests for engine/schema.py: data loading and validation failures."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from engine.schema import (
    Board,
    Concept,
    ConceptFilter,
    EffectAdapter,
    GameData,
    Quadrant,
    RolesFile,
    SchemaError,
    SkillsFile,
    load_game_data,
    parse_effect,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _minimal_board_kwargs(**overrides: object) -> dict:
    """A valid single quadrant's worth of board.yaml fields, for validator tests."""
    base = {
        "id": "discovery",
        "name": "Discovery",
        "order": 1,
        "milestone": {
            "id": "milestone_1",
            "name": "Milestone 1",
            "requirement": {"D": 3, "V": 2, "F": 1},
            "leads_to": "npd",
        },
        "spaces": ["D", "V", "F", "skills", "chance"] * 3,
    }
    base.update(overrides)
    return base


class TestLoadGameData:
    def test_all_data_loads(self) -> None:
        data = load_game_data(DATA_DIR)
        assert isinstance(data, GameData)

    def test_real_content_covers_the_rules_examples(self) -> None:
        """The Sheet-authored card library (tools/sync_content.py) has grown
        well past rules.md's original example cards -- checks the library
        still contains what rules.md cites directly, not that it matches
        those examples exactly (the Sheet is the ongoing source of truth,
        see the content pipeline plan)."""
        data = load_game_data(DATA_DIR)

        assert set(data.roles) == {"pm", "designer", "engineer", "researcher", "data_ml_engineer"}
        assert {"agile_methods", "scrum_master", "venture_capitalist"} <= set(data.skills)
        assert {"platform_play", "user_portal"} <= set(data.concepts)
        assert "budget_cuts" in data.chance_cards
        assert "smoke_testing" in {c.id for c in data.dvf_decks["discovery"].cards}

    def test_special_shorthand_normalized(self) -> None:
        data = load_game_data(DATA_DIR)
        agile = data.skills["agile_methods"]
        assert agile.effects[0].type == "special"
        assert agile.effects[0].handler == "agile_methods"

    def test_concept_modifier_semantics(self) -> None:
        data = load_game_data(DATA_DIR)
        platform_play = data.concepts["platform_play"]
        assert platform_play.tam == 5.0
        assert platform_play.modifiers[0].dim == "all"
        assert platform_play.modifiers[0].op == "multiply"
        assert platform_play.modifiers[0].value == 2


class TestUnknownEffectType:
    def test_unknown_primitive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EffectAdapter.validate_python({"type": "not_a_real_primitive"})

    def test_unknown_special_handler_rejected(self) -> None:
        with pytest.raises(ValidationError):
            parse_effect({"special": "not_a_real_handler"})

    def test_known_special_shorthand_accepted(self) -> None:
        effect = parse_effect({"special": "agile_methods"})
        assert effect.type == "special"
        assert effect.handler == "agile_methods"

    def test_special_effect_target_defaults_to_none(self) -> None:
        effect = parse_effect({"type": "special", "handler": "agile_methods"})
        assert effect.target is None

    def test_special_effect_target_parsed(self) -> None:
        effect = parse_effect(
            {"type": "special", "handler": "fetch_concept", "target": "platform_play"}
        )
        assert effect.target == "platform_play"


class TestCardWeight:
    """`weight` controls draw commonality (see the deck-construction plan);
    it's additive and optional on Skill/ChanceCard/DvfCard, never Concept."""

    def test_defaults_to_one_when_omitted(self) -> None:
        skills_file = SkillsFile.model_validate(
            {
                "skills": [
                    {
                        "id": "s",
                        "name": "S",
                        "eligible_roles": ["pm"],
                        "effects": [{"type": "buff", "dim": "D", "n": 1}],
                    }
                ]
            }
        )
        assert skills_file.skills[0].weight == 1

    def test_explicit_weight_accepted(self) -> None:
        skills_file = SkillsFile.model_validate(
            {
                "skills": [
                    {
                        "id": "s",
                        "name": "S",
                        "eligible_roles": ["pm"],
                        "effects": [{"type": "buff", "dim": "D", "n": 1}],
                        "weight": 5,
                    }
                ]
            }
        )
        assert skills_file.skills[0].weight == 5

    def test_zero_weight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SkillsFile.model_validate(
                {
                    "skills": [
                        {
                            "id": "s",
                            "name": "S",
                            "eligible_roles": ["pm"],
                            "effects": [{"type": "buff", "dim": "D", "n": 1}],
                            "weight": 0,
                        }
                    ]
                }
            )

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SkillsFile.model_validate(
                {
                    "skills": [
                        {
                            "id": "s",
                            "name": "S",
                            "eligible_roles": ["pm"],
                            "effects": [{"type": "buff", "dim": "D", "n": 1}],
                            "weight": -1,
                        }
                    ]
                }
            )


class TestConceptMedium:
    """A Concept can be physical AND/OR digital (rules.md), so `medium` is
    a list, matching `categories`' shape."""

    def test_multiple_mediums_accepted(self) -> None:
        concept = Concept(
            id="c", name="C", tam=1.0, medium=["physical", "digital"], categories=["product"]
        )
        assert concept.medium == ["physical", "digital"]

    def test_empty_medium_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Concept(id="c", name="C", tam=1.0, medium=[], categories=["product"])

    def test_duplicate_medium_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Concept(
                id="c", name="C", tam=1.0, medium=["digital", "digital"], categories=["product"]
            )


class TestUnknownRoleReference:
    def test_skill_eligible_role_unknown(self) -> None:
        skills_file = SkillsFile.model_validate(
            {
                "skills": [
                    {
                        "id": "bogus",
                        "name": "Bogus Skill",
                        "eligible_roles": ["not_a_real_role"],
                        "effects": [{"type": "buff", "dim": "D", "n": 1}],
                    }
                ]
            }
        )
        roles_file = RolesFile.model_validate({"roles": [{"id": "pm", "name": "Product Manager"}]})
        role_ids = {r.id for r in roles_file.roles}
        skill = skills_file.skills[0]
        assert not set(skill.eligible_roles) <= role_ids

    def test_loader_rejects_unknown_role_reference(self, tmp_path: Path) -> None:
        _write_data_dir(
            tmp_path,
            skills_override=[
                {
                    "id": "bogus",
                    "name": "Bogus Skill",
                    "eligible_roles": ["not_a_real_role"],
                    "effects": [{"type": "buff", "dim": "D", "n": 1}],
                }
            ],
        )
        with pytest.raises(SchemaError, match="unknown role"):
            load_game_data(tmp_path)

    def test_role_conditional_unknown_role_rejected(self, tmp_path: Path) -> None:
        _write_data_dir(
            tmp_path,
            chance_override=[
                {
                    "id": "weird_chance",
                    "name": "Weird Chance",
                    "effects": [
                        {
                            "type": "role_conditional",
                            "by_role": {
                                "not_a_real_role": [{"type": "add_tokens", "dim": "D", "n": 1}]
                            },
                        }
                    ],
                }
            ],
        )
        with pytest.raises(SchemaError, match="unknown role"):
            load_game_data(tmp_path)


class TestFetchConceptTarget:
    def test_missing_target_rejected(self, tmp_path: Path) -> None:
        _write_data_dir(
            tmp_path,
            chance_override=[
                {
                    "id": "test_fetch",
                    "name": "Test Fetch",
                    "effects": [{"type": "special", "handler": "fetch_concept"}],
                }
            ],
        )
        with pytest.raises(SchemaError, match="needs a target"):
            load_game_data(tmp_path)

    def test_unknown_target_rejected(self, tmp_path: Path) -> None:
        _write_data_dir(
            tmp_path,
            chance_override=[
                {
                    "id": "test_fetch",
                    "name": "Test Fetch",
                    "effects": [
                        {
                            "type": "special",
                            "handler": "fetch_concept",
                            "target": "not_a_real_concept",
                        }
                    ],
                }
            ],
        )
        with pytest.raises(SchemaError, match="not a known concept"):
            load_game_data(tmp_path)

    def test_valid_target_loads(self, tmp_path: Path) -> None:
        _write_data_dir(
            tmp_path,
            chance_override=[
                {
                    "id": "test_fetch",
                    "name": "Test Fetch",
                    "effects": [
                        {"type": "special", "handler": "fetch_concept", "target": "platform_play"}
                    ],
                }
            ],
        )
        data = load_game_data(tmp_path)
        assert "test_fetch" in data.chance_cards


class TestBoardValidation:
    def test_bad_leads_to_rejected(self, tmp_path: Path) -> None:
        _write_data_dir(tmp_path, leads_to_override="nowhere")
        with pytest.raises(SchemaError, match="unknown quadrant"):
            load_game_data(tmp_path)

    def test_space_count_enforced_not_fifteen(self) -> None:
        with pytest.raises(ValidationError):
            Quadrant.model_validate(_minimal_board_kwargs(spaces=["D", "V", "F"]))

    def test_space_count_enforced_wrong_distribution(self) -> None:
        with pytest.raises(ValidationError):
            Quadrant.model_validate(_minimal_board_kwargs(spaces=["D"] * 15))

    def test_board_requires_exactly_four_quadrants(self) -> None:
        with pytest.raises(ValidationError):
            Board.model_validate({"quadrants": [_minimal_board_kwargs()]})


class TestConceptFilterHypothesis:
    @given(
        medium=st.sampled_from(["digital", "physical", None]),
        category=st.sampled_from(["product", "service", "experience", None]),
    )
    def test_concept_filter_round_trips(self, medium: str | None, category: str | None) -> None:
        raw = {}
        if medium is not None:
            raw["medium"] = medium
        if category is not None:
            raw["category"] = category
        parsed = ConceptFilter.model_validate(raw)
        assert parsed.medium == medium
        assert parsed.category == category

    @given(dim=st.sampled_from(["D", "V", "F"]), n=st.integers(min_value=-10, max_value=10))
    def test_add_tokens_effect_round_trips(self, dim: str, n: int) -> None:
        effect = EffectAdapter.validate_python({"type": "add_tokens", "dim": dim, "n": n})
        assert effect.dim == dim
        assert effect.n == n


def _write_data_dir(
    tmp_path: Path,
    *,
    skills_override: list[dict] | None = None,
    chance_override: list[dict] | None = None,
    leads_to_override: str | None = None,
) -> None:
    """Copy the real data/ dir into tmp_path, optionally injecting a bad card."""
    import shutil

    import yaml

    shutil.copytree(DATA_DIR, tmp_path, dirs_exist_ok=True)

    if skills_override is not None:
        skills_path = tmp_path / "skills.yaml"
        content = yaml.safe_load(skills_path.read_text())
        content["skills"].extend(skills_override)
        skills_path.write_text(yaml.safe_dump(content))

    if chance_override is not None:
        chance_path = tmp_path / "chance.yaml"
        content = yaml.safe_load(chance_path.read_text())
        content["chance_cards"].extend(chance_override)
        chance_path.write_text(yaml.safe_dump(content))

    if leads_to_override is not None:
        board_path = tmp_path / "board.yaml"
        content = yaml.safe_load(board_path.read_text())
        content["quadrants"][0]["milestone"]["leads_to"] = leads_to_override
        board_path.write_text(yaml.safe_dump(content))
