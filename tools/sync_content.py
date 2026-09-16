"""Convert Google Sheets card data into data/*.yaml.

This module is deliberately Google-free: it takes rows already fetched
(however that happened) as plain `dict[str, str]` per row, keyed by
column header, and turns them into validated data/*.yaml files. Fetching
the rows from the actual spreadsheet happens elsewhere (in the session
doing the sync), keeping this half pure, testable, and free of any
runtime dependency on Google -- the engine only ever reads committed
YAML, same as before this pipeline existed.

Card decks map 1:1 to the tabs described in the content pipeline plan:
Roles, Skills, Concepts, Chance, DVF. `board.yaml` is not sheet-managed
(structural, rarely changes) -- it's read from the existing data dir to
validate against, and copied through unchanged.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from engine.schema import Board, load_game_data

ALL_ROLE_IDS = ("pm", "designer", "engineer", "researcher", "data_ml_engineer")


class ContentSyncError(Exception):
    """Raised when a sheet row can't be converted, naming the tab/row/card."""


# --- the effects DSL ---------------------------------------------------------
#
# One column, semicolon-separated effects, each "type key=value key=value ...".
# Dotted keys nest (buff's filter.medium / filter.category). Mirrors
# engine/schema.py's Effect union field-for-field -- not a second model.
# role_conditional isn't supported yet (rules/open-questions.md #13): no
# real card uses it, so there's nothing to design the nested syntax against.


def _coerce_scalar(raw: str) -> bool | int | float | str:
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _set_nested(target: dict, dotted_key: str, value: object) -> None:
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def parse_effect(effect_text: str) -> dict:
    """`"buff dim=D n=1 filter.category=service"` -> the raw effect dict
    engine/schema.py's Effect union expects."""
    tokens = effect_text.split()
    if not tokens:
        raise ValueError("empty effect")
    effect_type, *kv_tokens = tokens
    result: dict = {"type": effect_type}
    for token in kv_tokens:
        key, sep, raw_value = token.partition("=")
        if not sep:
            raise ValueError(f"expected key=value in '{token}' (effect: '{effect_text}')")
        _set_nested(result, key.strip(), _coerce_scalar(raw_value.strip()))
    return result


def parse_effects_cell(cell: str) -> list[dict]:
    cell = (cell or "").strip()
    if not cell:
        return []
    return [parse_effect(part.strip()) for part in cell.split(";") if part.strip()]


def _serialize_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _serialize_kv(prefix: str, value: object) -> list[str]:
    if isinstance(value, dict):
        tokens = []
        for key, nested in value.items():
            tokens.extend(_serialize_kv(f"{prefix}.{key}", nested))
        return tokens
    return [f"{prefix}={_serialize_scalar(value)}"]


def serialize_effect(effect: dict) -> str:
    """The inverse of `parse_effect` -- used to seed the sheet from
    existing data/*.yaml content, and exercised by the DSL round-trip
    test. Key order follows the dict's own order (Pydantic field
    declaration order via model_dump()), which is stable but not
    guaranteed to match hand-written DSL strings token-for-token."""
    parts = [effect["type"]]
    for key, value in effect.items():
        if key == "type":
            continue
        parts.extend(_serialize_kv(key, value))
    return " ".join(parts)


def serialize_effects(effects: list[dict]) -> str:
    return "; ".join(serialize_effect(e) for e in effects)


def parse_list_cell(cell: str) -> list[str]:
    cell = (cell or "").strip()
    if not cell:
        return []
    return [item.strip() for item in cell.split(",") if item.strip()]


def parse_eligible_roles(cell: str) -> list[str]:
    items = parse_list_cell(cell)
    if len(items) == 1 and items[0].lower() == "all":
        return list(ALL_ROLE_IDS)
    return items


# --- row -> card dict, one per deck -----------------------------------------


def _optional_text_fields(row: dict[str, str], card: dict) -> None:
    for field in ("flavor", "art"):
        value = (row.get(field) or "").strip()
        if value:
            card[field] = value


def role_row_to_dict(row: dict[str, str]) -> dict:
    card = {"id": row["id"].strip(), "name": row["name"].strip()}
    _optional_text_fields(row, card)
    return card


def skill_row_to_dict(row: dict[str, str]) -> dict:
    card = {
        "id": row["id"].strip(),
        "name": row["name"].strip(),
        "eligible_roles": parse_eligible_roles(row.get("eligible_roles", "")),
        "effects": parse_effects_cell(row.get("effects", "")),
    }
    _optional_text_fields(row, card)
    return card


def concept_row_to_dict(row: dict[str, str]) -> dict:
    card = {
        "id": row["id"].strip(),
        "name": row["name"].strip(),
        "tam": float(row["tam"]),
        "medium": row["medium"].strip(),
        "categories": parse_list_cell(row.get("categories", "")),
        "modifiers": parse_effects_cell(row.get("modifiers", "")),
    }
    _optional_text_fields(row, card)
    return card


def chance_row_to_dict(row: dict[str, str]) -> dict:
    card = {
        "id": row["id"].strip(),
        "name": row["name"].strip(),
        "effects": parse_effects_cell(row.get("effects", "")),
    }
    _optional_text_fields(row, card)
    return card


def dvf_row_to_dict(row: dict[str, str]) -> dict:
    card = {
        "id": row["id"].strip(),
        "name": row["name"].strip(),
        "dim": row["dim"].strip(),
        "effects": parse_effects_cell(row.get("effects", "")),
    }
    _optional_text_fields(row, card)
    return card


def _convert_rows(tab_name: str, rows: list[dict[str, str]], row_fn) -> list[dict]:
    converted = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            converted.append(row_fn(row))
        except Exception as exc:
            card_id = row.get("id", "?")
            raise ContentSyncError(f"{tab_name} tab, row {i} (id='{card_id}'): {exc}") from exc
    return converted


def _build_dvf_files(rows: list[dict[str, str]], quadrant_ids: list[str]) -> dict[str, dict]:
    by_quadrant: dict[str, list[dict]] = {q: [] for q in quadrant_ids}
    for i, row in enumerate(rows, start=2):
        quadrant = (row.get("quadrant") or "").strip()
        card_id = row.get("id", "?")
        if quadrant not in by_quadrant:
            raise ContentSyncError(
                f"DVF tab, row {i} (id='{card_id}'): unknown quadrant '{quadrant}', "
                f"expected one of {quadrant_ids}"
            )
        try:
            by_quadrant[quadrant].append(dvf_row_to_dict(row))
        except Exception as exc:
            raise ContentSyncError(f"DVF tab, row {i} (id='{card_id}'): {exc}") from exc
    return {
        f"dvf/{quadrant}.yaml": {"quadrant": quadrant, "cards": cards}
        for quadrant, cards in by_quadrant.items()
    }


# --- orchestration ------------------------------------------------------


@dataclass(frozen=True)
class SyncReport:
    roles: int
    skills: int
    concepts: int
    chance_cards: int
    dvf_cards: int


def sync_content(sheet_tabs: dict[str, list[dict[str, str]]], data_dir: Path | str) -> SyncReport:
    """Convert already-fetched sheet rows into data/*.yaml.

    `sheet_tabs` maps tab name ("Roles", "Skills", "Concepts", "Chance",
    "DVF") to its rows, each row a dict keyed by column header.

    Validates everything (via the same `load_game_data()` the engine
    itself uses) in a scratch directory before touching `data_dir` --  a
    bad row in the sheet never leaves it in a broken, half-written state.
    """
    data_dir = Path(data_dir)
    board = Board.model_validate(yaml.safe_load((data_dir / "board.yaml").read_text()))
    quadrant_ids = [q.id for q in board.quadrants]

    files: dict[str, dict] = {
        "roles.yaml": {
            "roles": _convert_rows("Roles", sheet_tabs.get("Roles", []), role_row_to_dict)
        },
        "skills.yaml": {
            "skills": _convert_rows("Skills", sheet_tabs.get("Skills", []), skill_row_to_dict)
        },
        "concepts.yaml": {
            "concepts": _convert_rows(
                "Concepts", sheet_tabs.get("Concepts", []), concept_row_to_dict
            )
        },
        "chance.yaml": {
            "chance_cards": _convert_rows(
                "Chance", sheet_tabs.get("Chance", []), chance_row_to_dict
            )
        },
        **_build_dvf_files(sheet_tabs.get("DVF", []), quadrant_ids),
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for rel_path, content in files.items():
            dest = tmp_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(yaml.safe_dump(content, sort_keys=False))
        shutil.copy(data_dir / "board.yaml", tmp_path / "board.yaml")

        game_data = load_game_data(tmp_path)  # raises SchemaError with full context on failure

        for rel_path in files:
            dest = data_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(tmp_path / rel_path, dest)

    return SyncReport(
        roles=len(game_data.roles),
        skills=len(game_data.skills),
        concepts=len(game_data.concepts),
        chance_cards=len(game_data.chance_cards),
        dvf_cards=sum(len(deck.cards) for deck in game_data.dvf_decks.values()),
    )
