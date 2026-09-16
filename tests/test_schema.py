"""Tests for engine/schema.py: data loading and validation failures."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from engine.schema import (
    Board,
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

    def test_every_rules_example_card_present(self) -> None:
        data = load_game_data(DATA_DIR)

        assert set(data.roles) == {"pm", "designer", "engineer", "researcher", "data_ml_engineer"}

        expected_skills = {
            "service_designer",
            "experience_designer",
            "journey_mapper",
            "user_researcher",
            "venture_capitalist",
            "agile_methods",
            "scrum_master",
        }
        assert set(data.skills) == expected_skills

        assert set(data.concepts) == {"platform_play", "user_portal"}
        assert set(data.chance_cards) == {"budget_cuts"}

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
