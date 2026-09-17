"""Tests for cli/game_loop.py: the mixed human/agent driver.

Points run_game_loop() at a real fastapi.testclient.TestClient -- no real
network or process -- since it satisfies the same .get/.post shape a real
httpx.Client would. No real Anthropic API calls either: agent seats use a
scripted fake client, same pattern as tests/test_llm_agent.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents.llm_agent import ActionChoice
from cli.game_loop import SeatConfig, run_game_loop
from server.app import app, get_game_data
from tests.fixtures import make_game_data

DATA = make_game_data(concept_count=8)


@pytest.fixture(autouse=True)
def _override_data():
    app.dependency_overrides[get_game_data] = lambda: DATA
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _new_game(client, player_ids, seed=1):
    response = client.post("/games", json={"player_ids": list(player_ids), "seed": seed})
    assert response.status_code == 200, response.text
    return response.json()["game_id"]


class _ScriptedInput:
    """Returns responses from a fixed list, one per call. Calling it past
    the end of the list raises StopIteration -- a loud failure if a seat
    that shouldn't be prompted is prompted anyway."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.call_count = 0

    def __call__(self, prompt: str) -> str:
        self.call_count += 1
        return next(self._responses)


class _FakeAnthropicResponse:
    def __init__(self, action_index: int, rationale: str = "because") -> None:
        self.parsed_output = ActionChoice(action_index=action_index, rationale=rationale)
        self.content = [{"type": "text", "text": "stub"}]


class _ScriptedAnthropicClient:
    """Same shape as tests/test_llm_agent.py's _ScriptedClient. Calling it
    past the end of the list raises StopIteration."""

    def __init__(self, responses: list[_FakeAnthropicResponse]) -> None:
        self._responses = iter(responses)
        self.call_count = 0
        self.messages = self

    def parse(self, **kwargs) -> _FakeAnthropicResponse:
        self.call_count += 1
        return next(self._responses)


class TestAllHumanGame:
    def test_scripted_input_advances_a_few_decisions(self, client) -> None:
        game_id = _new_game(client, ["alice", "bob"], seed=5)
        seats = [SeatConfig("alice", "human"), SeatConfig("bob", "human")]
        input_fn = _ScriptedInput(["0", "0", "0"])

        view = run_game_loop(
            client, game_id, seats, input_fn=input_fn, print_fn=lambda *a: None, max_steps=3
        )

        assert input_fn.call_count == 3
        # confirm the server-side game actually advanced, not just the
        # local loop's own bookkeeping
        assert client.get(f"/games/{game_id}").json() == view

    def test_invalid_input_is_rejected_and_reprompted(self, client) -> None:
        game_id = _new_game(client, ["alice"], seed=5)
        seats = [SeatConfig("alice", "human")]
        # "abc" (not a number), "99" (out of range), then a valid "0"
        input_fn = _ScriptedInput(["abc", "99", "0"])
        printed: list[str] = []

        run_game_loop(
            client, game_id, seats, input_fn=input_fn, print_fn=printed.append, max_steps=1
        )

        assert input_fn.call_count == 3
        assert any("isn't a valid choice" in line for line in printed)


class TestMixedHumanAgentGame:
    def test_agent_seat_handles_its_decision_without_prompting_a_human(self, client) -> None:
        game_id = _new_game(client, ["alice", "bob"], seed=5)
        active = client.get(f"/games/{game_id}").json()["decision_owner"]
        other = "bob" if active == "alice" else "alice"

        seats = [
            SeatConfig(active, "agent", model="claude-haiku-4-5-20251001"),
            SeatConfig(other, "human"),
        ]
        input_fn = _ScriptedInput([])  # must never be called
        anthropic_client = _ScriptedAnthropicClient([_FakeAnthropicResponse(0)])

        run_game_loop(
            client,
            game_id,
            seats,
            anthropic_client=anthropic_client,
            rules_text="rules text",
            input_fn=input_fn,
            print_fn=lambda *a: None,
            max_steps=1,
        )

        assert anthropic_client.call_count == 1
        assert input_fn.call_count == 0

    def test_human_seat_handles_its_decision_without_calling_the_llm(self, client) -> None:
        game_id = _new_game(client, ["alice", "bob"], seed=5)
        active = client.get(f"/games/{game_id}").json()["decision_owner"]
        other = "bob" if active == "alice" else "alice"

        seats = [
            SeatConfig(active, "human"),
            SeatConfig(other, "agent", model="claude-haiku-4-5-20251001"),
        ]
        input_fn = _ScriptedInput(["0"])
        anthropic_client = _ScriptedAnthropicClient([])  # must never be called

        run_game_loop(
            client,
            game_id,
            seats,
            anthropic_client=anthropic_client,
            rules_text="rules text",
            input_fn=input_fn,
            print_fn=lambda *a: None,
            max_steps=1,
        )

        assert input_fn.call_count == 1
        assert anthropic_client.call_count == 0

    def test_unconfigured_seat_raises_a_clear_error(self, client) -> None:
        game_id = _new_game(client, ["alice", "bob"], seed=5)
        active = client.get(f"/games/{game_id}").json()["decision_owner"]
        other = "bob" if active == "alice" else "alice"
        seats = [SeatConfig(other, "human")]  # nobody configured for `active`

        with pytest.raises(KeyError, match=active):
            run_game_loop(client, game_id, seats, input_fn=lambda p: "0", max_steps=1)
