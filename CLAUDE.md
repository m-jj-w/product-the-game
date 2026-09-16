# CLAUDE.md: Product: The Game  
  
## What this project is  
  
"Product: The Game" is a collaborative board game about product management. Players act as one team against the game, moving a Portfolio of product Concepts through four quadrants (Discovery, New Product Development, Scaling, Market Maturity). The goal is to bank at least $1B in TAM within 50 turns.  
  
This repo contains:  
  
1. A rules engine that is the only authority on game rules.  
2. Game content written as data in YAML.  
3. AI players: random, heuristic, and LLM-based.  
4. A simulation runner for testing balance.  
5. A web multiplayer server and client, built later.  
  
**The canonical rules are in `rules/rules.md`.** If code and rules disagree, the rules are correct unless the discrepancy has been logged and resolved in `rules/open-questions.md`.  
  
## Non-negotiable principles  
  
1. **The engine owns legality.** Agents, the UI, and the server never decide whether a move is legal. They choose from what the engine offers.  
2. **Game content is data.** Every card, space, role, and requirement lives in `data/*.yaml`. Engine code must not mention specific card names.  
3. **Special-case code goes through a registry.** When a card can't be expressed with the effect primitives, write a named handler in `engine/special/` and reference it from YAML by name, for example `special: agile_methods`. Keep these rare.  
4. **All randomness is seeded.** Dice, shuffles, and role deals all use one RNG stored in the game state. A seed plus a list of actions must replay a game exactly.  
5. **Don't guess at the rules.** If the rules are unclear or silent, stop and add an entry to `rules/open-questions.md` that describes the situation, the options, and the provisional choice. Implement the provisional choice behind a clearly named config flag, then keep going.  
6. **Game state is immutable.** `apply()` returns a new state. This makes simulation, undo, and tree search simple.  
7. **Build in thin slices.** Every milestone ends with passing tests. Don't start the next slice while tests are failing.  
  
## Architecture  
  
```  
rules/ rules.md (canonical), open-questions.md  
data/ board.yaml, roles.yaml, skills.yaml, concepts.yaml,  
 chance.yaml, dvf/{discovery,npd,scaling,maturity}.yaml  
engine/  
 schema.py Pydantic models for all YAML; validate at load time  
 state.py GameState, Concept, Player, Decks (frozen dataclasses)  
 effects.py effect primitive registry  
 modifiers.py milestone requirement calculation  
 rules.py legal_actions, apply  
 engine.py public API  
 special/ named handlers for cards the primitives can't express  
agents/ random_agent.py, greedy_agent.py, llm_agent.py  
sim/ batch runner, metrics, reports  
server/ FastAPI + websockets (later); thin web client  
tests/  
```  
  
### Public engine API  
  
```python  
new_game(config, seed) -> GameState  
legal_actions(state) -> list[Action] # for the current decision owner  
apply(state, action) -> GameState  
observe(state, player_id) -> str # plain-text view for humans/LLMs  
current_decision(state) -> Decision # what's being decided, and who decides  
is_over(state) -> Outcome | None # win / loss (with reason) / None  
```  
  
### Decisions  
  
Every point where the game pauses for a choice is a typed `Decision` with an owner.  
  
| Decision | Owner |  
|---|---|  
| Choose Concept and direction to move | Active player |  
| Cross a Milestone (if qualified) | Active player |  
| Accept, discard, or give away a drawn Skill | Active player |  
| Use Scrum Master | Holder, on their own turn only |  
| Close phase: remove or add Concepts; team role swap | Team (PM decides) |  
| Choose target for "team's choice" Chance cards | Team (PM decides) |  
  
Treat the Close phase as a sequence of small actions ending with `end_close`, rather than listing every possible combination. The same approach applies to any choice with many combinations.  
  
### Effect primitives (starting set; extend when needed)  
  
- `add_tokens {dim, n}` (n can be negative)  
- `modify_requirement {dim | all, add | multiply, quadrant?}`  
- `buff {dim, n, filter}`, where filter matches Concept attributes such as digital/physical and product/service/experience  
- `remove_concept {chooser: team}`  
- `draw_concept {n}`  
- `move_concept {n | to}`  
- `role_swap {…}`  
- `extra_turn`, `delegate_turn` (Agile Methods and Scrum Master, likely registry handlers)  
- `role_conditional {role: effect}` (for Chance cards that affect roles differently)  
  
### Milestone requirement calculation (order matters)  
  
For each dimension:  
  
```  
required = (base[quadrant][dim] × concept_multipliers) + concept_additions  
have = concept_tokens[dim] + sum(applicable Skill buffs) # all buffs stack  
qualifies = have >= required for all of D, V, F  
```  
  
## Key rule decisions  
  
These are already settled. Don't reopen them without logging a question.  
  
- The 50-turn limit counts turns across the whole team. An Agile Methods double turn counts as 1.  
- Each quadrant has 15 coded spaces (3 each of D, V, F, Skills, Chance) plus one blank Gateway, which is both the entry and the exit. Landing on a Gateway triggers nothing.  
- A qualifying Concept can cross a Milestone when its movement reaches or passes the Gateway. It stops on the next quadrant's Gateway, and leftover movement is lost. Crossing is optional.  
- Tokens have no cap and can go negative. They reset to 0 when a Milestone is crossed. Removing a Concept wipes its tokens, including debt.  
- New Concepts **always** enter at the Discovery Gateway.  
- The Portfolio holds 1 to 5 active Concepts. A Concept at Finish leaves the Portfolio and its TAM goes to the bank.  
- **Win:** the TAM bank reaches at least $1B.  
- **Loss:** the 50 turns run out; the last active Concept is removed; or the last active Concept reaches Finish while the bank is under $1B.  
- The PM role is dealt at random, other roles are dealt at random, and no two players share a role. The team's decisions are made by the PM.  
- A player holds one permanent Skill, and a new Skill replaces the old one (which is discarded). If the drawn Skill doesn't fit the player's role, they either discard it and continue, or give it to an eligible player, which ends their turn immediately with no Close phase.  
- Agile Methods gives two full turns every turn. Scrum Master is usable once per turn, on the holder's own turn only.  
- The team role swap unlocks when all active Concepts have passed Product Market Fit, and it can be used only in the Close phase immediately after that.  
- Chance cards target the Concept that landed on the space unless the card says otherwise.  
- All cards are public. Concepts can share spaces. Empty decks reshuffle their discards.  
  
## Known balance concerns (test these in simulation)  
  
- **Agile Methods** may be too strong, since it roughly doubles the holder's actions.  
- **Debt wiping** could make "remove and replace" the best response to bad draws.  
- **Stacking buffs** could make late-game milestones trivial.  
- **The team role swap** may almost never be earned, because new Concepts enter at Discovery.  
- **Platform Play** (×2 requirements, $5B) may be all-or-nothing and could make up most of the win rate.  
  
## Build plan  
  
1. Write the Pydantic schema and YAML loader/validator, with sample data covering every example card. Tests confirm that every YAML file loads and every effect maps to a known primitive or registry handler.  
2. Build the core loop with no cards: setup, move, Gateways, milestones, turn counter, win and loss. Tests use seeded games.  
3. Add the DVF decks and quadrant sub-decks.  
4. Add the Close phase and Portfolio rules (1 to 5 limit, entry, removal, Finish, and the bank).  
5. Add Skills, then Chance cards, then the special handlers (Agile Methods, Scrum Master, role swaps).  
6. Write the random and greedy agents, then the simulation runner. It should report game length, win rate, reasons for losses, portfolio churn, and how much each card affects the win rate.  
7. Build the LLM agent. It receives the rules as prose, a text view of the state, and a numbered list of legal actions. It returns an action ID and a short rationale. If it picks an illegal action, it gets another prompt with the error. Every choice is logged.  
8. Build the web server and client.  
  
## Testing requirements  
  
- **Invariants (property tests):** active Portfolio size stays between 1 and 5 until the game ends; the turn counter never decreases; replaying the same seed and actions gives an identical game; every `apply()` input came from `legal_actions()`.  
- **Scenario tests** for every rule in "Key rule decisions."  
- Run `pytest` before declaring any step done.  
  
## Conventions  
  
- Python 3.12+, type hints everywhere, `ruff` for linting and formatting, `pytest` for tests.  
- Keep functions small and pure. No global state.  
- Write clear docstrings for anything an LLM agent or UI will read through `observe()`.  
