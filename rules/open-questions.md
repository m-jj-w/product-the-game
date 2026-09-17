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

## 7. Loop overflow for a non-qualifying Concept (resolved)

Rules §8.1.2 says a Concept always moves "the full amount rolled," with no
exception for a move that would carry it past the last coded space. §9.3
only describes what happens when a *qualifying* Concept crosses a
Milestone (it stops on the next quadrant's Gateway, leftover movement
lost) — it's silent on a non-qualifying Concept in the same situation.

**Resolved with the user:** because the path is a loop, a non-qualifying
Concept's move simply continues around it — the Gateway is a pass-through
space (no draw) in that direction, exactly like any other quadrant it
isn't currently exiting through. Concepts can move in either direction on
any given roll, so a Concept can pass the Gateway before it qualifies, and
change direction later to actually cross once it does qualify.

Implemented in `engine/rules.py`: a move that would land at or past the
Gateway (`raw >= 16` in the 16-slot loop model, offset 0 = Gateway) auto-
wraps (`new_offset = raw % 16`) unless the Concept qualifies for the
quadrant's Milestone, in which case it gets an explicit accept/decline
cross decision (declining also wraps). Backward movement past the
Gateway always wraps and never offers crossing.

## 8. Scrum Master: turn rotation after delegation (resolved)

Rules §10 says the Scrum Master holder "may hand the rest of the turn to
another player," but doesn't say what happens to turn order afterward:
does the next turn continue from the delegate's seat, or return to the
original holder's?

**Resolved with the user:** rotation snaps back to the original holder's
seat. Delegation only reassigns who's currently making decisions for the
rest of this turn, not whose turn *slot* it is.

Implemented via two separate fields on `GameState`: `turn_owner_index`
(whose turn slot this is — drives rotation math and the Agile Methods
bonus-cycle check) and `active_player_index` (who's currently deciding —
what `DelegateTurn` reassigns). Every new Move phase (a real turn start,
or an Agile Methods bonus cycle) resets `active_player_index` back to
`turn_owner_index`, so each cycle starts with the owner back in control
even if the previous cycle ended mid-delegation.

## 9. "May take it" for an eligible Skill

Rules §10 describes the ineligible-Skill branch with an explicit choice
(discard and continue, or give to an eligible teammate). The eligible
branch just says "the player may take it," with no stated alternative if
they don't.

**Provisional choice:** read as permissive ("they're allowed to," in
contrast to the ineligible case where they aren't), not as an optional
decision. Taking an eligible Skill is automatic — no decision point, no
choice to decline and discard it instead.

## 10. Agile Methods picked up mid-turn

Rules §10 says Agile Methods "applies on every one of the holder's
turns," but doesn't address a player who draws it partway through a turn
that's already in progress.

**Provisional choice:** the check happens at end-of-cycle time, against
whichever Skill the holder currently has. If a player draws Agile
Methods during what would otherwise be a normal turn, finishing that
cycle immediately grants the bonus second cycle, same turn.

## 11. Chained Scrum Master delegation

If the Scrum Master holder delegates to a player who *also* holds Scrum
Master, could that second player delegate again in the same turn slot?
Rules §10's "once per turn" isn't explicit about whether it's scoped per
holder or per turn.

**Provisional choice:** allowed, not specially blocked. Each holder can
use their own Scrum Master once while they're the one currently
deciding; nothing in the rules prohibits a chain, and blocking it would
require inventing a restriction the text doesn't state.

## 12. Role swap: earn-once, use-it-or-lose-it

Rules §3 says the team earns a role swap "when every active Concept has
passed the Product Market Fit Milestone," used immediately in the Close
phase that follows "or it is lost." It doesn't say what happens if the
condition remains true on later turns too (all Concepts stay past PMF
indefinitely once they cross it) — is a fresh swap earned every such
Close phase, or is it truly a one-time-ever grant?

**Provisional choice:** one-time-ever. `role_swap_used` and
`role_swap_forfeited` are both permanent, one-way latches: the swap is
offered the first Close phase the condition holds, and if not used by
`end_close`, `role_swap_forfeited` permanently blocks it from coming
back — even though the quadrant condition will typically stay true for
the rest of the game.

## 13. `role_conditional` effect DSL encoding

The Sheets -> YAML content pipeline (`tools/sync_content.py`) needs a
compact per-cell syntax for every effect type. `role_conditional` is the
one exception: it's recursive (`by_role: {role_id: list[Effect]}`, each
nested effect potentially needing the same DSL), and no real card uses it
yet, so there's no concrete example to design the syntax against.

**Provisional choice:** not designed yet. The DSL currently covers
`add_tokens`, `modify_requirement`, `buff`, `remove_concept`,
`draw_concept`, `move_concept`, `role_swap`, and `special`. A Chance card
needing `role_conditional` will need this revisited first — don't guess
at a nested syntax with nothing real to validate it against.

## 14. Sick Day: "skip the current player's turn"

The card is drawn mid-move (the landing Concept already moved to trigger
the Chance draw), so a literal "the turn never happened" reading doesn't
fit the sequence of events.

**Provisional choice:** read as "skip this turn's Close phase and end
the turn immediately" — the Move/Draw that already happened stands, but
there's no team decision-making afterward. Implemented via
`GameState.pending_skip_close`, checked in `_enter_close_phase`.

## 15. Productivity / Retrospective: reusing the Agile Methods bonus cycle

Both cards grant a "go again" turn (Productivity for the current player,
Retrospective for the *next* one) with no other stated mechanical
difference from Agile Methods' "two complete turns count as one"
(rules.md sec 10).

**Provisional choice:** implemented as one-shot triggers into the exact
same bonus-cycle machinery Agile Methods uses (`GameState.
pending_extra_turn` for Productivity, consumed in `_end_turn` the same
way `_holds_special(..., "agile_methods")` is; `pending_double_next_turn`
for Retrospective, carried across the next rotation and converted to
`pending_extra_turn` for the new turn owner). If a turn owner somehow
holds Agile Methods *and* has a Chance-card bonus queued the same turn,
only one bonus cycle is granted (the fields aren't additive) — not
expected to come up, since Agile Methods already grants a bonus every
turn its holder has it.

## 16. Portfolio capacity bounds (Expanded/Narrowed Scope)

CLAUDE.md's "Portfolio holds 1 to 5 active Concepts" is stated as a fixed
rule; these two cards make the upper bound variable per-game.

**Provisional choice:** `GameState.portfolio_capacity` starts at 5 and is
only adjusted by these two cards. Narrowed Scope floors it at 1 (can
never force zero capacity); no ceiling on Expanded Scope, since the rules
don't state one. The absolute minimum of 1 active Concept (loss
condition if it hits 0) is unrelated and stays hardcoded.

## 17. Research Breakthrough: token top-up scope

"Add as many tokens as necessary... to achieve the next Milestone" could
mean topping up to the base requirement only, or accounting for the
team's current Skill buffs too (which `qualifies()` already factors in
for an actual Milestone crossing).

**Provisional choice:** tops up to the *base* `required_dvf()` value
only, ignoring Skill buffs — simpler, and a real crossing attempt still
adds buffs on top via the normal `qualifies()` check. All `(Concept,
dim)` pairs are offered as options even when the gain would be 0 (dim
already met); a rational team won't pick a no-op.

## 18. Fetch Concept (e.g. Pet Project): target not found

If the target Concept id isn't in `concept_deck.draw_pile` or
`discard_pile` (e.g. it's already active in the Portfolio, or was
already fetched earlier in the same game), the card has nothing to do.

**Provisional choice:** fizzles silently — the Chance card is still
discarded as used, but no Concept is added. Not expected to come up in
practice (each such Concept exists once), but handled rather than
raising, since "the target happens to already be on the board" is a
legitimate game state, not a data error.
