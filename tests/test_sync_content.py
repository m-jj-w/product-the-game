"""Tests for tools/sync_content.py: the effects DSL and the sheet -> YAML sync."""

from pathlib import Path

import pytest
import yaml

from engine.schema import SchemaError, load_game_data
from tests.fixtures import make_board
from tools.sync_content import (
    ContentSyncError,
    concept_row_to_dict,
    dvf_row_to_dict,
    parse_effect,
    parse_effects_cell,
    parse_eligible_roles,
    parse_list_cell,
    role_row_to_dict,
    serialize_effect,
    serialize_effects,
    skill_row_to_dict,
    sync_content,
)


class TestParseEffect:
    def test_add_tokens(self) -> None:
        assert parse_effect("add_tokens dim=D n=1") == {"type": "add_tokens", "dim": "D", "n": 1}

    def test_modify_requirement(self) -> None:
        assert parse_effect("modify_requirement dim=all op=multiply value=2") == {
            "type": "modify_requirement",
            "dim": "all",
            "op": "multiply",
            "value": 2,
        }

    def test_buff_with_nested_filter(self) -> None:
        assert parse_effect("buff dim=D n=1 filter.category=service") == {
            "type": "buff",
            "dim": "D",
            "n": 1,
            "filter": {"category": "service"},
        }

    def test_buff_with_two_filter_keys(self) -> None:
        result = parse_effect("buff dim=V n=2 filter.medium=digital filter.category=product")
        assert result == {
            "type": "buff",
            "dim": "V",
            "n": 2,
            "filter": {"medium": "digital", "category": "product"},
        }

    def test_remove_concept(self) -> None:
        assert parse_effect("remove_concept chooser=team") == {
            "type": "remove_concept",
            "chooser": "team",
        }

    def test_special(self) -> None:
        assert parse_effect("special handler=agile_methods") == {
            "type": "special",
            "handler": "agile_methods",
        }

    def test_role_swap(self) -> None:
        assert parse_effect("role_swap chooser=team") == {"type": "role_swap", "chooser": "team"}

    def test_draw_concept_no_args(self) -> None:
        assert parse_effect("draw_concept") == {"type": "draw_concept"}

    def test_move_concept(self) -> None:
        assert parse_effect("move_concept n=3") == {"type": "move_concept", "n": 3}

    def test_negative_number_coerced(self) -> None:
        assert parse_effect("add_tokens dim=D n=-2") == {"type": "add_tokens", "dim": "D", "n": -2}

    def test_malformed_token_without_equals_raises(self) -> None:
        with pytest.raises(ValueError, match="expected key=value"):
            parse_effect("add_tokens dim")

    def test_empty_effect_raises(self) -> None:
        with pytest.raises(ValueError, match="empty effect"):
            parse_effect("")


class TestParseEffectsCell:
    def test_multiple_effects_semicolon_separated(self) -> None:
        cell = "buff dim=D n=1 filter.category=service; buff dim=F n=1 filter.category=service"
        result = parse_effects_cell(cell)
        assert result == [
            {"type": "buff", "dim": "D", "n": 1, "filter": {"category": "service"}},
            {"type": "buff", "dim": "F", "n": 1, "filter": {"category": "service"}},
        ]

    def test_empty_cell_gives_empty_list(self) -> None:
        assert parse_effects_cell("") == []
        assert parse_effects_cell("   ") == []

    def test_trailing_semicolon_ignored(self) -> None:
        assert parse_effects_cell("add_tokens dim=D n=1;") == [
            {"type": "add_tokens", "dim": "D", "n": 1}
        ]


class TestSerializeEffectRoundTrip:
    @pytest.mark.parametrize(
        "effect",
        [
            {"type": "add_tokens", "dim": "D", "n": 1},
            {"type": "add_tokens", "dim": "D", "n": -3},
            {"type": "modify_requirement", "dim": "all", "op": "multiply", "value": 2},
            {"type": "buff", "dim": "D", "n": 1, "filter": {"category": "service"}},
            {
                "type": "buff",
                "dim": "V",
                "n": 2,
                "filter": {"medium": "digital", "category": "product"},
            },
            {"type": "remove_concept", "chooser": "team"},
            {"type": "special", "handler": "agile_methods"},
        ],
    )
    def test_round_trips_through_serialize_and_parse(self, effect: dict) -> None:
        assert parse_effect(serialize_effect(effect)) == effect

    def test_serialize_effects_joins_with_semicolons(self) -> None:
        effects = [{"type": "add_tokens", "dim": "D", "n": 1}, {"type": "special", "handler": "x"}]
        assert serialize_effects(effects) == "add_tokens dim=D n=1; special handler=x"
        assert parse_effects_cell(serialize_effects(effects)) == effects


class TestParseListCells:
    def test_parse_list_cell(self) -> None:
        assert parse_list_cell("designer, researcher") == ["designer", "researcher"]
        assert parse_list_cell("") == []

    def test_eligible_roles_all_expands(self) -> None:
        assert parse_eligible_roles("all") == [
            "pm",
            "designer",
            "engineer",
            "researcher",
            "data_ml_engineer",
        ]

    def test_eligible_roles_specific_list_passes_through(self) -> None:
        assert parse_eligible_roles("designer, researcher") == ["designer", "researcher"]


class TestRowToDict:
    def test_role_row_omits_blank_optional_fields(self) -> None:
        row = {"id": "pm", "name": "Product Manager", "flavor": "", "art": ""}
        assert role_row_to_dict(row) == {"id": "pm", "name": "Product Manager"}

    def test_role_row_includes_populated_optional_fields(self) -> None:
        row = {"id": "pm", "name": "Product Manager", "flavor": "Leads the team", "art": "pm.png"}
        assert role_row_to_dict(row) == {
            "id": "pm",
            "name": "Product Manager",
            "flavor": "Leads the team",
            "art": "pm.png",
        }

    def test_skill_row(self) -> None:
        row = {
            "id": "service_designer",
            "name": "Service Designer",
            "eligible_roles": "designer",
            "effects": (
                "buff dim=D n=1 filter.category=service; buff dim=F n=1 filter.category=service"
            ),
            "flavor": "",
            "art": "",
        }
        result = skill_row_to_dict(row)
        assert result["eligible_roles"] == ["designer"]
        assert len(result["effects"]) == 2

    def test_concept_row(self) -> None:
        row = {
            "id": "platform_play",
            "name": "Platform Play",
            "tam": "5.0",
            "medium": "digital",
            "categories": "product,service,experience",
            "modifiers": "modify_requirement dim=all op=multiply value=2",
            "flavor": "Twice the work, twice the fun.",
            "art": "",
        }
        result = concept_row_to_dict(row)
        assert result["tam"] == 5.0
        assert result["categories"] == ["product", "service", "experience"]
        assert result["modifiers"] == [
            {"type": "modify_requirement", "dim": "all", "op": "multiply", "value": 2}
        ]

    def test_dvf_row(self) -> None:
        row = {
            "id": "smoke_testing",
            "name": "Smoke Testing",
            "dim": "D",
            "quadrant": "discovery",
            "effects": "add_tokens dim=D n=1",
            "flavor": "",
            "art": "",
        }
        result = dvf_row_to_dict(row)
        assert result == {
            "id": "smoke_testing",
            "name": "Smoke Testing",
            "dim": "D",
            "effects": [{"type": "add_tokens", "dim": "D", "n": 1}],
        }

    def test_dvf_row_blank_weight_omitted(self) -> None:
        row = {
            "id": "smoke_testing",
            "name": "Smoke Testing",
            "dim": "D",
            "quadrant": "discovery",
            "effects": "add_tokens dim=D n=1",
            "flavor": "",
            "art": "",
            "weight": "",
        }
        assert "weight" not in dvf_row_to_dict(row)

    def test_dvf_row_explicit_weight_parsed(self) -> None:
        row = {
            "id": "smoke_testing",
            "name": "Smoke Testing",
            "dim": "D",
            "quadrant": "discovery",
            "effects": "add_tokens dim=D n=1",
            "flavor": "",
            "art": "",
            "weight": "3",
        }
        assert dvf_row_to_dict(row)["weight"] == 3


def _seed_board(data_dir: Path) -> None:
    board = make_board()
    (data_dir / "board.yaml").write_text(yaml.safe_dump(board.model_dump(), sort_keys=False))


_VALID_SHEET = {
    "Roles": [
        {"id": "pm", "name": "Product Manager", "flavor": "", "art": ""},
        {"id": "designer", "name": "Designer", "flavor": "", "art": ""},
    ],
    "Skills": [
        {
            "id": "service_designer",
            "name": "Service Designer",
            "eligible_roles": "designer",
            "effects": "buff dim=D n=1 filter.category=service",
            "flavor": "",
            "art": "",
        }
    ],
    "Concepts": [
        {
            "id": "platform_play",
            "name": "Platform Play",
            "tam": "5.0",
            "medium": "digital",
            "categories": "product,service,experience",
            "modifiers": "modify_requirement dim=all op=multiply value=2",
            "flavor": "",
            "art": "",
        }
    ],
    "Chance": [
        {
            "id": "budget_cuts",
            "name": "Budget Cuts",
            "effects": "remove_concept chooser=team",
            "flavor": "",
            "art": "",
        }
    ],
    "DVF": [
        {
            "id": "smoke_testing",
            "name": "Smoke Testing",
            "dim": "D",
            "quadrant": "discovery",
            "effects": "add_tokens dim=D n=1",
            "flavor": "",
            "art": "",
        }
    ],
}


class TestSyncContent:
    def test_valid_sheet_produces_loadable_data(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        report = sync_content(_VALID_SHEET, tmp_path)
        assert report.roles == 2
        assert report.skills == 1
        assert report.concepts == 1
        assert report.chance_cards == 1
        assert report.dvf_cards == 1

        data = load_game_data(tmp_path)
        assert "platform_play" in data.concepts
        assert data.concepts["platform_play"].tam == 5.0

    def test_explicit_weight_column_round_trips_to_loaded_data(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        sheet = {
            **_VALID_SHEET,
            "DVF": [{**_VALID_SHEET["DVF"][0], "weight": "3"}],
        }
        sync_content(sheet, tmp_path)
        data = load_game_data(tmp_path)
        assert data.dvf_decks["discovery"].cards[0].weight == 3

    def test_blank_weight_column_defaults_to_one(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        sync_content(_VALID_SHEET, tmp_path)  # _VALID_SHEET rows have no "weight" key at all
        data = load_game_data(tmp_path)
        assert data.dvf_decks["discovery"].cards[0].weight == 1

    def test_all_four_quadrant_files_written_even_when_empty(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        sync_content(_VALID_SHEET, tmp_path)
        for quadrant in ("discovery", "npd", "scaling", "market_maturity"):
            assert (tmp_path / "dvf" / f"{quadrant}.yaml").exists()
        npd_content = yaml.safe_load((tmp_path / "dvf" / "npd.yaml").read_text())
        assert npd_content == {"quadrant": "npd", "cards": []}

    def test_unknown_quadrant_raises_clear_error(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        bad_sheet = {**_VALID_SHEET, "DVF": [{**_VALID_SHEET["DVF"][0], "quadrant": "mars"}]}
        with pytest.raises(ContentSyncError, match="unknown quadrant 'mars'"):
            sync_content(bad_sheet, tmp_path)

    def test_malformed_effect_names_the_row_and_card(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        bad_sheet = {
            **_VALID_SHEET,
            "Skills": [{**_VALID_SHEET["Skills"][0], "effects": "buff dim"}],
        }
        with pytest.raises(ContentSyncError, match="Skills tab, row 2.*service_designer"):
            sync_content(bad_sheet, tmp_path)

    def test_bad_row_leaves_data_dir_untouched(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        # A first, valid sync to establish a known-good state.
        sync_content(_VALID_SHEET, tmp_path)
        before = (tmp_path / "concepts.yaml").read_text()

        bad_sheet = {
            **_VALID_SHEET,
            "Concepts": [{**_VALID_SHEET["Concepts"][0], "tam": "not-a-number"}],
        }
        with pytest.raises(ContentSyncError):
            sync_content(bad_sheet, tmp_path)

        assert (tmp_path / "concepts.yaml").read_text() == before

    def test_schema_validation_failure_surfaces_as_schema_error(self, tmp_path: Path) -> None:
        _seed_board(tmp_path)
        # A skill referencing a role that doesn't exist -- passes DSL
        # parsing but fails load_game_data()'s cross-file check.
        bad_sheet = {
            **_VALID_SHEET,
            "Skills": [{**_VALID_SHEET["Skills"][0], "eligible_roles": "not_a_real_role"}],
        }
        with pytest.raises(SchemaError, match="unknown role"):
            sync_content(bad_sheet, tmp_path)
