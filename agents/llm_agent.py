"""The LLM agent: plays every decision in a game via the Claude API.

CLAUDE.md's build plan step 7: "It receives the rules as prose, a text
view of the state, and a numbered list of legal actions. It returns an
action ID and a short rationale. If it picks an illegal action, it gets
another prompt with the error. Every choice is logged."

The game is cooperative with per-decision owners (active player for
Move/CrossMilestone/Skill, PM for Close/chance_removal -- see
engine/engine.py's current_decision). This first version plays every
decision with one agent instance, told who it's deciding as via the
prompt; distinct per-player personas are a natural later extension, not
needed for a first working agent.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.engine import NewGameConfig, apply, current_decision, is_over, new_game, observe
from engine.rules import (
    Action,
    ChanceRemoveConcept,
    CrossMilestone,
    Decision,
    DelegateTurn,
    DiscardSkill,
    DrawConcept,
    EndClose,
    GiveSkill,
    MoveConcept,
    Outcome,
    RemoveConcept,
    RoleSwap,
)
from engine.state import GameState

RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.md"
DEFAULT_MODEL = "claude-opus-5"


class ActionChoice(BaseModel):
    """The structured response shape requested via client.messages.parse()."""

    action_index: int
    rationale: str


def describe_action(action: Action, state: GameState) -> str:
    """Human-readable text for one legal Action, resolving ids to names."""
    if isinstance(action, MoveConcept):
        card = state.data.concepts[action.concept_id]
        return f"Move '{card.name}' {action.direction}"
    if isinstance(action, CrossMilestone):
        card = state.data.concepts[action.concept_id]
        verb = "Cross the Milestone with" if action.cross else "Decline crossing for"
        return f"{verb} '{card.name}'"
    if isinstance(action, RemoveConcept):
        card = state.data.concepts[action.concept_id]
        return f"Remove '{card.name}' from the Portfolio"
    if isinstance(action, DrawConcept):
        return "Draw a new Concept onto the Discovery Gateway"
    if isinstance(action, EndClose):
        return "End the Close phase (end the turn)"
    if isinstance(action, DiscardSkill):
        skill = state.data.skills[state.pending_skill]
        return f"Discard the drawn Skill '{skill.name}'"
    if isinstance(action, GiveSkill):
        skill = state.data.skills[state.pending_skill]
        return f"Give the drawn Skill '{skill.name}' to {action.recipient_id}"
    if isinstance(action, ChanceRemoveConcept):
        card = state.data.concepts[action.concept_id]
        return f"Remove '{card.name}' (Chance card effect)"
    if isinstance(action, DelegateTurn):
        return f"Delegate the rest of this turn to {action.recipient_id} (Scrum Master)"
    if isinstance(action, RoleSwap):
        return f"Swap roles between {action.player_a_id} and {action.player_b_id}"
    raise TypeError(f"no description for action type: {type(action)!r}")


def _build_prompt(state: GameState, decision: Decision, descriptions: list[str]) -> str:
    numbered = "\n".join(f"{i}. {desc}" for i, desc in enumerate(descriptions))
    return (
        f"{observe(state, decision.owner)}\n\n"
        f"You are deciding as: {decision.owner} ({decision.kind} decision).\n\n"
        f"Choose one of the following actions by its number:\n{numbered}\n\n"
        "Respond with the action_index and a short rationale."
    )


def choose_action(
    client: Any,
    rules_text: str,
    state: GameState,
    decision: Decision,
    descriptions: list[str],
    *,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
) -> tuple[Action, str, int]:
    """Ask the LLM to pick one of `decision.actions`. Retries with the error
    appended if it picks an out-of-range index. Returns (action, rationale,
    attempts_taken)."""
    prompt = _build_prompt(state, decision, descriptions)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    system = [{"type": "text", "text": rules_text, "cache_control": {"type": "ephemeral"}}]

    for attempt in range(1, max_retries + 1):
        response = client.messages.parse(
            model=model,
            max_tokens=1024,
            system=system,
            messages=messages,
            output_format=ActionChoice,
        )
        choice = response.parsed_output
        if 0 <= choice.action_index < len(descriptions):
            return decision.actions[choice.action_index], choice.rationale, attempt

        messages.append({"role": "assistant", "content": response.content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"'{choice.action_index}' is not a valid action index. "
                    f"Choose an integer from 0 to {len(descriptions) - 1}."
                ),
            }
        )

    raise RuntimeError(
        f"LLM failed to choose a valid action after {max_retries} attempts "
        f"(decision: {decision.kind}, owner: {decision.owner})"
    )


@dataclass(frozen=True)
class ChoiceLogEntry:
    turn: int
    decision_kind: str
    owner: str
    observation: str
    options: list[str]
    chosen_index: int
    chosen_description: str
    rationale: str
    attempts: int


@dataclass(frozen=True)
class GameLog:
    seed: int
    outcome: Outcome | None
    choices: list[ChoiceLogEntry] = field(default_factory=list)


def run_llm_game(
    config: NewGameConfig,
    seed: int,
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
    max_choices: int = 500,
    log_path: Path | str | None = None,
) -> GameLog:
    """Play one full game turn-by-turn via the LLM, logging every choice.

    `max_choices` is a hard safety cap so a stuck game can't spin forever
    burning API calls. `client` defaults to a real anthropic.Anthropic()
    if not given -- pass a fake for tests.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    rules_text = RULES_PATH.read_text()
    state = new_game(config, seed)
    entries: list[ChoiceLogEntry] = []
    log_file = open(log_path, "w") if log_path else None

    try:
        for _ in range(max_choices):
            if is_over(state) is not None:
                break

            decision = current_decision(state)
            assert decision is not None
            actions = list(decision.actions)
            descriptions = [describe_action(a, state) for a in actions]
            observation = observe(state, decision.owner)

            action, rationale, attempts = choose_action(
                client,
                rules_text,
                state,
                decision,
                descriptions,
                model=model,
                max_retries=max_retries,
            )
            chosen_index = actions.index(action)

            entry = ChoiceLogEntry(
                turn=state.turn,
                decision_kind=decision.kind,
                owner=decision.owner,
                observation=observation,
                options=descriptions,
                chosen_index=chosen_index,
                chosen_description=descriptions[chosen_index],
                rationale=rationale,
                attempts=attempts,
            )
            entries.append(entry)
            if log_file:
                log_file.write(json.dumps(dataclasses.asdict(entry)) + "\n")
                log_file.flush()

            state = apply(state, action)
        else:
            raise RuntimeError(f"game exceeded {max_choices} choices without ending")
    finally:
        if log_file:
            log_file.close()

    return GameLog(seed=seed, outcome=is_over(state), choices=entries)
