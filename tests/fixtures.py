"""Synthetic GameData for engine tests.

Deliberately NOT the real data/ dir: this reuses the real board shape
(rules.md's 4 quadrants and milestone requirements) but with generic
concept cards, since data/concepts.yaml only has the 2 example cards from
the rules (not enough for a 5-concept starting Portfolio). See
rules/open-questions.md and CLAUDE.md's "don't guess" principle — this
fixture exists so engine mechanics can be tested without inventing real
card content.
"""

from __future__ import annotations

from engine.schema import (
    Board,
    Concept,
    DvfCard,
    DvfDeck,
    DVFRequirement,
    GameData,
    Milestone,
    Quadrant,
    Role,
    Skill,
)

_SPACES = ["D", "V", "F", "skills", "chance"] * 3

_ROLE_NAMES = [
    ("pm", "Product Manager"),
    ("designer", "Designer"),
    ("engineer", "Engineer"),
    ("researcher", "Researcher"),
    ("data_ml_engineer", "Data & ML Engineer"),
]


def make_board() -> Board:
    return Board(
        quadrants=[
            Quadrant(
                id="discovery",
                name="Discovery",
                order=1,
                milestone=Milestone(
                    id="milestone_1",
                    name="Milestone 1",
                    requirement=DVFRequirement(D=3, V=2, F=1),
                    leads_to="npd",
                ),
                spaces=_SPACES,
            ),
            Quadrant(
                id="npd",
                name="New Product Development",
                order=2,
                milestone=Milestone(
                    id="product_market_fit",
                    name="Product Market Fit Milestone",
                    requirement=DVFRequirement(D=2, V=2, F=2),
                    leads_to="scaling",
                ),
                spaces=_SPACES,
            ),
            Quadrant(
                id="scaling",
                name="Scaling",
                order=3,
                milestone=Milestone(
                    id="milestone_3",
                    name="Milestone 3",
                    requirement=DVFRequirement(D=1, V=2, F=3),
                    leads_to="market_maturity",
                ),
                spaces=_SPACES,
            ),
            Quadrant(
                id="market_maturity",
                name="Market Maturity",
                order=4,
                milestone=Milestone(
                    id="milestone_4",
                    name="Milestone 4",
                    requirement=DVFRequirement(D=0, V=3, F=2),
                    leads_to="finish",
                ),
                spaces=_SPACES,
            ),
        ]
    )


def make_roles() -> dict[str, Role]:
    return {role_id: Role(id=role_id, name=name) for role_id, name in _ROLE_NAMES}


def make_concepts(count: int = 6) -> dict[str, Concept]:
    return {
        f"concept_{i}": Concept(
            id=f"concept_{i}",
            name=f"Test Concept {i}",
            tam=0.3,
            medium="digital",
            categories=["product"],
        )
        for i in range(count)
    }


_ALL_ROLE_IDS = [rid for rid, _ in _ROLE_NAMES]


def make_skills() -> dict[str, Skill]:
    """A small synthetic Skill set: one role-restricted buff, one buff with
    a medium filter, one all-roles buff, and the two special Skills (their
    `special:` YAML shorthand only expands during YAML loading, so the
    explicit `{type: special, handler: ...}` form is used here)."""
    return {
        "designer_buff": Skill(
            id="designer_buff",
            name="Designer Buff",
            eligible_roles=["designer"],
            effects=[{"type": "buff", "dim": "D", "n": 1}],
        ),
        "pm_digital_buff": Skill(
            id="pm_digital_buff",
            name="PM Digital Buff",
            eligible_roles=["pm"],
            effects=[{"type": "buff", "dim": "V", "n": 2, "filter": {"medium": "digital"}}],
        ),
        "all_roles_buff": Skill(
            id="all_roles_buff",
            name="All Roles Buff",
            eligible_roles=list(_ALL_ROLE_IDS),
            effects=[{"type": "buff", "dim": "F", "n": 1}],
        ),
        "agile_methods": Skill(
            id="agile_methods",
            name="Agile Methods",
            eligible_roles=list(_ALL_ROLE_IDS),
            effects=[{"type": "special", "handler": "agile_methods"}],
        ),
        "scrum_master": Skill(
            id="scrum_master",
            name="Scrum Master",
            eligible_roles=list(_ALL_ROLE_IDS),
            effects=[{"type": "special", "handler": "scrum_master"}],
        ),
    }


_QUADRANT_IDS = ("discovery", "npd", "scaling", "market_maturity")


def make_dvf_decks(*, cards_per_dim: int = 2) -> dict[str, DvfDeck]:
    """2 generic add_tokens cards per (quadrant, dim) -- enough to exercise
    real draw/discard/reshuffle mechanics without inventing rules content."""
    decks: dict[str, DvfDeck] = {}
    for quadrant_id in _QUADRANT_IDS:
        cards = [
            DvfCard(
                id=f"{quadrant_id}_{dim}_{i}",
                name=f"{quadrant_id} {dim} card {i}",
                dim=dim,
                effects=[{"type": "add_tokens", "dim": dim, "n": 1}],
            )
            for dim in ("D", "V", "F")
            for i in range(cards_per_dim)
        ]
        decks[quadrant_id] = DvfDeck(quadrant=quadrant_id, cards=cards)
    return decks


def make_game_data(
    *, concept_count: int = 6, dvf_decks: dict[str, DvfDeck] | None = None
) -> GameData:
    return GameData(
        roles=make_roles(),
        skills=make_skills(),
        concepts=make_concepts(concept_count),
        chance_cards={},
        dvf_decks=dvf_decks if dvf_decks is not None else make_dvf_decks(),
        board=make_board(),
    )
