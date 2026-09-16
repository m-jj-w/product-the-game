"""Tests for agents/llm_agent.py: describe_action, choose_action, run_llm_game.

None of these hit the real Anthropic API -- every test uses a fake client
stubbing `.messages.parse()`.
"""

from __future__ import annotations

import random
import re

import pytest

from agents.llm_agent import (
    ActionChoice,
    ChoiceLogEntry,
    GameLog,
    choose_action,
    describe_action,
    run_llm_game,
)
from engine.engine import NewGameConfig
from engine.rules import (
    ChanceRemoveConcept,
    CrossMilestone,
    Decision,
    DelegateTurn,
    DiscardSkill,
    DrawConcept,
    EndClose,
    GiveSkill,
    MoveConcept,
    RemoveConcept,
    RoleSwap,
)
from engine.state import BoardPosition, ConceptInstance, GameState, Player
from tests.fixtures import make_game_data

DATA = make_game_data()


def _state(pending_skill: str | None = None) -> GameState:
    return GameState(
        data=DATA,
        turn=0,
        active_player_index=0,
        turn_owner_index=0,
        players=(Player(id="alice", role_id="pm"), Player(id="bob", role_id="designer")),
        portfolio=(
            ConceptInstance(card_id="concept_0", position=BoardPosition("discovery", 1)),
            ConceptInstance(card_id="concept_1", position=BoardPosition("discovery", 1)),
        ),
        bank=0.0,
        rng_state=random.Random(0).getstate(),
        pending_skill=pending_skill,
    )


class TestDescribeAction:
    def test_move_concept(self) -> None:
        state = _state()
        desc = describe_action(MoveConcept("concept_0", "forward"), state)
        assert "Test Concept 0" in desc and "forward" in desc

    def test_cross_milestone_accept_and_decline(self) -> None:
        state = _state()
        accept = describe_action(CrossMilestone("concept_0", True), state)
        decline = describe_action(CrossMilestone("concept_0", False), state)
        assert "Cross" in accept
        assert "Decline" in decline

    def test_remove_concept(self) -> None:
        state = _state()
        desc = describe_action(RemoveConcept("concept_0"), state)
        assert "Remove" in desc and "Test Concept 0" in desc

    def test_draw_concept(self) -> None:
        desc = describe_action(DrawConcept(), _state())
        assert "Draw" in desc

    def test_end_close(self) -> None:
        desc = describe_action(EndClose(), _state())
        assert desc == "End the Close phase (end the turn)"

    def test_discard_skill_uses_pending_skill(self) -> None:
        state = _state(pending_skill="designer_buff")
        desc = describe_action(DiscardSkill(), state)
        assert "Designer Buff" in desc

    def test_give_skill_names_recipient_and_skill(self) -> None:
        state = _state(pending_skill="designer_buff")
        desc = describe_action(GiveSkill("bob"), state)
        assert "Designer Buff" in desc and "bob" in desc

    def test_chance_remove_concept(self) -> None:
        desc = describe_action(ChanceRemoveConcept("concept_1"), _state())
        assert "Remove" in desc and "Chance card" in desc

    def test_delegate_turn(self) -> None:
        desc = describe_action(DelegateTurn("bob"), _state())
        assert "Scrum Master" in desc and "bob" in desc

    def test_role_swap(self) -> None:
        desc = describe_action(RoleSwap("alice", "bob"), _state())
        assert "alice" in desc and "bob" in desc


class _FakeResponse:
    def __init__(self, action_index: int, rationale: str = "because") -> None:
        self.parsed_output = ActionChoice(action_index=action_index, rationale=rationale)
        self.content = [{"type": "text", "text": "stub"}]


class _ScriptedClient:
    """Returns responses from a fixed list, one per call. Raises if exhausted."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = iter(responses)
        self.call_count = 0
        self.messages = self

    def parse(self, **kwargs) -> _FakeResponse:
        self.call_count += 1
        return next(self._responses)


def _move_decision(state: GameState) -> Decision:
    actions = (MoveConcept("concept_0", "forward"), MoveConcept("concept_0", "backward"))
    return Decision(kind="move", owner="alice", actions=actions)


class TestChooseAction:
    def test_valid_first_response(self) -> None:
        state = _state()
        decision = _move_decision(state)
        descriptions = [describe_action(a, state) for a in decision.actions]
        client = _ScriptedClient([_FakeResponse(1, "good reason")])

        action, rationale, attempts = choose_action(
            client, "rules text", state, decision, descriptions
        )
        assert action == decision.actions[1]
        assert rationale == "good reason"
        assert attempts == 1
        assert client.call_count == 1

    def test_invalid_then_valid_retries_once(self) -> None:
        state = _state()
        decision = _move_decision(state)
        descriptions = [describe_action(a, state) for a in decision.actions]
        client = _ScriptedClient([_FakeResponse(99, "oops"), _FakeResponse(0, "corrected")])

        action, rationale, attempts = choose_action(
            client, "rules text", state, decision, descriptions
        )
        assert action == decision.actions[0]
        assert rationale == "corrected"
        assert attempts == 2
        assert client.call_count == 2

    def test_exhausting_retries_raises_with_context(self) -> None:
        state = _state()
        decision = _move_decision(state)
        descriptions = [describe_action(a, state) for a in decision.actions]
        client = _ScriptedClient([_FakeResponse(99, "x") for _ in range(3)])

        with pytest.raises(RuntimeError, match="move.*alice") as exc_info:
            choose_action(client, "rules text", state, decision, descriptions, max_retries=3)
        assert client.call_count == 3
        assert "3 attempts" in str(exc_info.value)


def _index_of_option(prompt: str, description: str) -> int | None:
    match = re.search(rf"^(\d+)\. {re.escape(description)}$", prompt, re.MULTILINE)
    return int(match.group(1)) if match else None


class _PreferEndCloseClient:
    """Always ends the Close phase promptly (avoids the remove/draw
    oscillation a naive 'always pick 0' policy would hit), picks index 0
    otherwise. No network calls -- purely used to smoke-test a full game
    loop's wiring."""

    def __init__(self) -> None:
        self.call_count = 0
        self.messages = self

    def parse(self, *, messages, **kwargs) -> _FakeResponse:
        self.call_count += 1
        prompt = messages[0]["content"]
        index = _index_of_option(prompt, "End the Close phase (end the turn)")
        return _FakeResponse(index if index is not None else 0)


class TestRunLlmGame:
    def test_full_game_runs_to_completion_and_logs_every_choice(self) -> None:
        data = make_game_data(concept_count=8)
        config = NewGameConfig(data=data, player_ids=["alice", "bob", "carol"])
        client = _PreferEndCloseClient()

        log = run_llm_game(config, seed=7, client=client, max_choices=500)

        assert isinstance(log, GameLog)
        assert log.outcome is not None
        assert log.outcome.result in ("win", "loss")
        assert len(log.choices) > 0
        assert client.call_count == len(log.choices)
        assert all(isinstance(c, ChoiceLogEntry) for c in log.choices)
        # every logged choice's index is within the options it was offered
        for choice in log.choices:
            assert 0 <= choice.chosen_index < len(choice.options)

    def test_logs_written_to_jsonl_incrementally(self, tmp_path) -> None:
        import json

        data = make_game_data(concept_count=8)
        config = NewGameConfig(data=data, player_ids=["alice", "bob"])
        client = _PreferEndCloseClient()
        log_path = tmp_path / "game.jsonl"

        log = run_llm_game(config, seed=3, client=client, max_choices=500, log_path=log_path)

        lines = log_path.read_text().splitlines()
        assert len(lines) == len(log.choices)
        first = json.loads(lines[0])
        assert first["decision_kind"] == log.choices[0].decision_kind
        assert first["owner"] == log.choices[0].owner

    def test_max_choices_safety_cap_raises(self) -> None:
        data = make_game_data(concept_count=8)
        config = NewGameConfig(data=data, player_ids=["alice"])
        client = _PreferEndCloseClient()

        with pytest.raises(RuntimeError, match="exceeded 1 choices"):
            run_llm_game(config, seed=1, client=client, max_choices=1)
