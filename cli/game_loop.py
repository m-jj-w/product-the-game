"""The mixed human/agent game loop -- a pure HTTP client of server/app.py.

No engine import: everything here comes from the same JSON GameView
server/app.py already serves to the web UI (observation text, the
decision's owner/kind, and its numbered options). That's deliberate --
an agent-controlled seat interacts with the game exactly the way a
remote human client eventually will, through the backend, not via a
shortcut straight into the engine.

`http` is anything with `.get(url)` / `.post(url, json=...)` returning an
object with `.raise_for_status()` and `.json()` -- an `httpx.Client`
(cli/play.py) and a `fastapi.testclient.TestClient` (tests) both already
satisfy that, so this module never needs to know which one it's holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agents.llm_agent import choose_action_index

_RULE = "=" * 60


@dataclass(frozen=True)
class SeatConfig:
    """Which of the game's players this run controls, and how."""

    player_id: str
    kind: Literal["human", "agent"]
    model: str | None = None  # agent seats only


def _seat_for(seats: list[SeatConfig], player_id: str) -> SeatConfig:
    for seat in seats:
        if seat.player_id == player_id:
            return seat
    raise KeyError(f"no seat configured for player '{player_id}'")


def _prompt_human_choice(view: dict, *, input_fn: Any, print_fn: Any) -> int:
    print_fn("")
    print_fn(view["observation"])
    print_fn("")
    for option in view["options"]:
        print_fn(f"  {option['index']}. {option['description']}")

    while True:
        raw = input_fn(f"\n{view['decision_owner']}, choose an action: ").strip()
        if raw.isdigit() and int(raw) < len(view["options"]):
            return int(raw)
        print_fn(f"'{raw}' isn't a valid choice -- enter a number from the list above.")


def _agent_choice(
    view: dict,
    seat: SeatConfig,
    *,
    anthropic_client: Any,
    rules_text: str,
    max_retries: int,
    print_fn: Any,
) -> int:
    descriptions = [o["description"] for o in view["options"]]
    index, rationale, _ = choose_action_index(
        anthropic_client,
        rules_text,
        view["observation"],
        view["decision_kind"],
        view["decision_owner"],
        descriptions,
        model=seat.model,
        max_retries=max_retries,
    )
    print_fn(
        f"\n{view['decision_owner']} (agent, {seat.model}) chooses: {descriptions[index]}\n"
        f'  "{rationale}"'
    )
    return index


def run_game_loop(
    http: Any,
    game_id: str,
    seats: list[SeatConfig],
    *,
    anthropic_client: Any = None,
    rules_text: str = "",
    input_fn: Any = input,
    print_fn: Any = print,
    max_retries: int = 3,
    max_steps: int | None = None,
) -> dict:
    """Drive `game_id` toward completion, routing each decision to whichever
    human/agent seat currently owns it. Returns the latest GameView --
    either once `outcome` is set, or after `max_steps` decisions if given
    (a testing/safety valve; the CLI itself always leaves it unbounded)."""
    steps = 0
    while True:
        response = http.get(f"/games/{game_id}")
        response.raise_for_status()
        view = response.json()

        if view["outcome"] is not None:
            print_fn("")
            print_fn(_RULE)
            outcome = view["outcome"]
            print_fn(f"GAME OVER: {outcome['result'].upper()} -- {outcome['reason']}")
            print_fn(_RULE)
            return view

        if max_steps is not None and steps >= max_steps:
            return view

        seat = _seat_for(seats, view["decision_owner"])
        if seat.kind == "human":
            index = _prompt_human_choice(view, input_fn=input_fn, print_fn=print_fn)
        else:
            index = _agent_choice(
                view,
                seat,
                anthropic_client=anthropic_client,
                rules_text=rules_text,
                max_retries=max_retries,
                print_fn=print_fn,
            )

        post_response = http.post(f"/games/{game_id}/actions", json={"action_index": index})
        post_response.raise_for_status()
        steps += 1
