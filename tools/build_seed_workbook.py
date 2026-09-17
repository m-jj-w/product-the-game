"""Build an .xlsx workbook from data/*.yaml, laid out to match the content
pipeline's sheet columns (see tools/sync_content.py). One-time (or
occasional reset) bootstrap: after this, the sheet itself is the source
of truth for card content, edited directly in Google Sheets.

Usage:
    python -m tools.build_seed_workbook [output_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from engine.schema import GameData, load_game_data
from tools.sync_content import serialize_effects

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _write_tab(wb: Workbook, title: str, header: list[str], rows: list[list[object]]) -> None:
    ws: Worksheet = wb.create_sheet(title=title)
    ws.append(header)
    for row in rows:
        ws.append(row)


def build_workbook(data: GameData) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)  # drop the default blank sheet

    _write_tab(
        wb,
        "Roles",
        ["id", "name", "flavor", "art"],
        [[r.id, r.name, r.flavor or "", r.art or ""] for r in data.roles.values()],
    )

    _write_tab(
        wb,
        "Skills",
        ["id", "name", "flavor", "eligible_roles", "effects", "art", "weight"],
        [
            [
                s.id,
                s.name,
                s.flavor or "",
                ",".join(s.eligible_roles),
                serialize_effects([e.model_dump(exclude_none=True) for e in s.effects]),
                s.art or "",
                s.weight,
            ]
            for s in data.skills.values()
        ],
    )

    _write_tab(
        wb,
        "Concepts",
        ["id", "name", "flavor", "tam", "medium", "categories", "modifiers", "art"],
        [
            [
                c.id,
                c.name,
                c.flavor or "",
                c.tam,
                ",".join(c.medium),
                ",".join(c.categories),
                serialize_effects([m.model_dump(exclude_none=True) for m in c.modifiers]),
                c.art or "",
            ]
            for c in data.concepts.values()
        ],
    )

    _write_tab(
        wb,
        "Chance",
        ["id", "name", "flavor", "effects", "art", "weight"],
        [
            [
                card.id,
                card.name,
                card.flavor or "",
                serialize_effects([e.model_dump(exclude_none=True) for e in card.effects]),
                card.art or "",
                card.weight,
            ]
            for card in data.chance_cards.values()
        ],
    )

    dvf_rows = []
    for quadrant, deck in data.dvf_decks.items():
        for card in deck.cards:
            dvf_rows.append(
                [
                    card.id,
                    card.name,
                    card.flavor or "",
                    quadrant,
                    card.dim,
                    serialize_effects([e.model_dump(exclude_none=True) for e in card.effects]),
                    card.art or "",
                    card.weight,
                ]
            )
    _write_tab(
        wb,
        "DVF",
        ["id", "name", "flavor", "quadrant", "dim", "effects", "art", "weight"],
        dvf_rows,
    )

    return wb


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("seed_workbook.xlsx")
    data = load_game_data(DATA_DIR)
    wb = build_workbook(data)
    wb.save(output_path)
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
