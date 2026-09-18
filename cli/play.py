"""Terminal client for Product: The Game.

A pure HTTP client of server/app.py -- start the server first:

    uvicorn server.app:app --host 127.0.0.1 --port 8420

then run this against it:

    python -m cli.play

Works with any mix of human and AI-controlled seats. An all-human game
never touches the Anthropic SDK or needs an API key.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from agents.llm_agent import RULES_PATH
from cli.game_loop import SeatConfig, run_game_loop

DEFAULT_BASE_URL = "http://127.0.0.1:8420"
DEFAULT_AGENT_MODEL = "claude-haiku-4-5-20251001"

_BANNER = """
\033[36m============================================================
  P R O D U C T :   T H E   G A M E
============================================================\033[0m
"""


def _prompt_int(prompt: str, *, default: int, lo: int, hi: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"Enter a number from {lo} to {hi}.")


def _prompt_kind(player_id: str) -> str:
    kind = ""
    while kind not in ("h", "a"):
        kind = input(f"  Is {player_id} (h)uman or an (a)gent? [h]: ").strip().lower() or "h"
    return "agent" if kind == "a" else "human"


def _assign_agent_models(seats: list[SeatConfig]) -> list[SeatConfig]:
    if not any(s.kind == "agent" for s in seats):
        return seats
    model = input(f"Model for agent seats [{DEFAULT_AGENT_MODEL}]: ").strip()
    model = model or DEFAULT_AGENT_MODEL
    return [
        SeatConfig(player_id=s.player_id, kind=s.kind, model=model) if s.kind == "agent" else s
        for s in seats
    ]


def _prompt_new_game_seats() -> list[SeatConfig]:
    count = _prompt_int("How many players (1-5)?", default=3, lo=1, hi=5)
    seats = []
    for i in range(1, count + 1):
        name = input(f"Player {i} name [p{i}]: ").strip() or f"p{i}"
        seats.append(SeatConfig(player_id=name, kind=_prompt_kind(name)))
    return _assign_agent_models(seats)


def _prompt_existing_game_seats(http: httpx.Client, game_id: str) -> list[SeatConfig]:
    response = http.get(f"/api/games/{game_id}")
    response.raise_for_status()
    player_ids = [p["id"] for p in response.json()["players"]]
    print(f"Joining game {game_id} -- players: {', '.join(player_ids)}")
    seats = [SeatConfig(player_id=pid, kind=_prompt_kind(pid)) for pid in player_ids]
    return _assign_agent_models(seats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--game-id", default=None, help="Join an existing game instead of creating one"
    )
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    print(_BANNER)

    http = httpx.Client(base_url=args.base_url, timeout=30.0)
    try:
        http.get("/api/board")
    except httpx.ConnectError:
        print(f"Can't reach the server at {args.base_url}.")
        print("Start it first: uvicorn server.app:app --host 127.0.0.1 --port 8420")
        sys.exit(1)

    if args.game_id:
        game_id = args.game_id
        seats = _prompt_existing_game_seats(http, game_id)
    else:
        seats = _prompt_new_game_seats()
        payload: dict = {"player_ids": [s.player_id for s in seats]}
        if args.seed is not None:
            payload["seed"] = args.seed
        response = http.post("/api/games", json=payload)
        if response.status_code != 200:
            print(f"Couldn't create game: {response.json().get('detail')}")
            sys.exit(1)
        game_id = response.json()["game_id"]
        print(f"\nGame {game_id} created.")

    anthropic_client = None
    rules_text = ""
    if any(s.kind == "agent" for s in seats):
        import anthropic

        anthropic_client = anthropic.Anthropic()
        rules_text = RULES_PATH.read_text()

    run_game_loop(http, game_id, seats, anthropic_client=anthropic_client, rules_text=rules_text)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(1)
