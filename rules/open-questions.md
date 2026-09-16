# Open questions

Log of places where `rules/rules.md` is silent or ambiguous. Each entry has a
provisional choice, implemented behind a clear placeholder, so work can keep
moving without guessing at canon.

## 1. Order of the 15 coded spaces per loop

Rules §12 explicitly lists this as unresolved: "The order of the 15 coded
spaces within each loop (fixed or randomized)."

**Provisional choice:** every quadrant in `data/board.yaml` uses the same
fixed repeating pattern `[D, V, F, skills, chance] × 3`. This is a
placeholder ordering, not a design decision — revisit once the board is
actually playtested.

## 2. Which quadrant's DVF sub-deck "Smoke Testing" belongs to

Rules §11 gives "Smoke Testing" as an example Desirability card but doesn't
tag it with a quadrant, even though DVF decks are split into per-quadrant
sub-decks (§5).

**Provisional choice:** placed in `data/dvf/discovery.yaml`, since smoke
testing is a discovery-stage validation technique. `npd.yaml`, `scaling.yaml`,
and `maturity.yaml` start empty (`cards: []`) pending real card lists.

## 3. Role card flavor text

Rules §5 says Role Cards "describe each of the five roles" but no
description text is given anywhere in the document.

**Provisional choice:** `data/roles.yaml` entries have `id` and `name` only;
no `flavor` field is populated.

## 4. Skills for Engineer and Data & ML Engineer roles

Rules §12 explicitly flags this as an open item: "Complete card lists for
all decks, including Skills for the Engineer and Data & ML Engineer roles."

**Provisional choice:** not inventing placeholder skills. Those two roles
currently have zero eligible Skills in `data/skills.yaml`.

## 5. `role_swap` effect shape

CLAUDE.md's effect-primitive list includes `role_swap {…}` with the fields
left as an ellipsis. No example Chance card in the rules actually
instantiates a role-swap effect — the only role swap the rules describe in
detail is the team-earned swap after Product Market Fit, which is a
structural rule (§3), not a card effect.

**Provisional choice:** minimal shape `{type: role_swap, chooser: team}` in
`engine/schema.py`. Revisit once a concrete Chance card needs more (e.g.
naming specific roles to swap).

## 6. Where global constants live

The 50-turn limit, the $1B win threshold, the 1–5 portfolio size bounds, and
the 5-concept starting draw are game-wide constants, not cards — CLAUDE.md's
data-is-data principle covers "every card, space, role, and requirement,"
which these aren't quite.

**Provisional choice:** these will be plain Python constants in a later
engine step, not YAML. Flagged here in case that turns out to be wrong once
the core loop (build plan step 2) is underway.
