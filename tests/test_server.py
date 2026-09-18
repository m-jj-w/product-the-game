"""Tests for server/app.py: the JSON API.

Uses FastAPI's TestClient (no real network) -- tests/conftest.py
overrides get_game_data/get_game_store with fakes, so these don't
depend on the real data/ dir's current content or on Firestore.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from agents.llm_agent import SPACE_LABELS
from server.app import app, get_game_data
from tests.fixtures import make_game_data


@pytest.fixture
def client():
    return TestClient(app)


def _new_game(client, player_ids=("alice", "bob"), seed=1):
    response = client.post("/api/games", json={"player_ids": list(player_ids), "seed": seed})
    assert response.status_code == 200, response.text
    return response.json()


class TestCreateGame:
    def test_returns_expected_shape(self, client) -> None:
        view = _new_game(client, ("alice", "bob"), seed=42)
        assert view["seed"] == 42
        assert view["turn"] == 0
        assert len(view["players"]) == 2
        assert len(view["portfolio"]) == 5
        assert view["decision_kind"] == "move"
        assert view["decision_owner"] in ("alice", "bob")
        assert view["outcome"] is None
        assert len(view["options"]) > 0
        assert view["history"] == []
        assert re.match(r"^[0-9a-f-]{36}$", view["game_id"])

    def test_random_seed_when_omitted(self, client) -> None:
        response = client.post("/api/games", json={"player_ids": ["alice"]})
        assert response.status_code == 200
        assert isinstance(response.json()["seed"], int)

    def test_invalid_request_surfaces_engine_message(self, client) -> None:
        response = client.post("/api/games", json={"player_ids": []})
        assert response.status_code == 400
        assert "1-5" in response.json()["detail"]

    def test_too_few_concepts_surfaces_engine_message(self, client) -> None:
        small_data = make_game_data(concept_count=2)
        app.dependency_overrides[get_game_data] = lambda: small_data
        response = client.post("/api/games", json={"player_ids": ["alice"]})
        assert response.status_code == 400
        assert "concepts" in response.json()["detail"]


class TestGetGame:
    def test_unknown_game_id_returns_404(self, client) -> None:
        response = client.get("/api/games/does-not-exist")
        assert response.status_code == 404

    def test_returns_same_view_without_mutating(self, client) -> None:
        created = _new_game(client)
        first = client.get(f"/api/games/{created['game_id']}").json()
        second = client.get(f"/api/games/{created['game_id']}").json()
        assert first == second


class TestChooseAction:
    def test_applying_legal_action_advances_state(self, client) -> None:
        view = _new_game(client, seed=5)
        result = client.post(f"/api/games/{view['game_id']}/actions", json={"action_index": 0})
        assert result.status_code == 200
        new_view = result.json()
        assert new_view["decision_kind"] in (
            "move",
            "close",
            "cross_milestone",
            "skill",
            "chance_removal",
        )
        assert new_view["outcome"] is None

    def test_out_of_range_index_returns_400(self, client) -> None:
        view = _new_game(client)
        result = client.post(f"/api/games/{view['game_id']}/actions", json={"action_index": 9999})
        assert result.status_code == 400
        assert "action_index" in result.json()["detail"]

    def test_unknown_game_id_returns_404(self, client) -> None:
        result = client.post("/api/games/nope/actions", json={"action_index": 0})
        assert result.status_code == 404


class TestShortPlaythrough:
    def test_reaches_both_move_and_close_decisions(self, client) -> None:
        view = _new_game(client, ("alice", "bob", "carol"), seed=9)
        seen_kinds = {view["decision_kind"]}

        for _ in range(30):
            if view["outcome"] is not None:
                break
            # Prefer ending the Close phase promptly so the game actually
            # progresses turn to turn instead of oscillating on
            # remove/draw (same trap noted in agents/llm_agent.py's tests).
            index = next(
                (o["index"] for o in view["options"] if "End the Close phase" in o["description"]),
                view["options"][0]["index"],
            )
            result = client.post(
                f"/api/games/{view['game_id']}/actions", json={"action_index": index}
            )
            assert result.status_code == 200
            view = result.json()
            seen_kinds.add(view["decision_kind"])

        assert "move" in seen_kinds
        assert "close" in seen_kinds


class TestBoard:
    def test_returns_four_quadrants_in_order_with_full_layout(self, client) -> None:
        response = client.get("/api/board")
        assert response.status_code == 200
        body = response.json()
        assert [q["order"] for q in body["quadrants"]] == [1, 2, 3, 4]
        assert [q["id"] for q in body["quadrants"]] == [
            "discovery",
            "npd",
            "scaling",
            "market_maturity",
        ]
        for q in body["quadrants"]:
            assert len(q["spaces"]) == 15
            assert q["milestone_name"]
            assert set(q["milestone_requirement"]) == {"D", "V", "F"}


class TestConcepts:
    def test_returns_every_concept_with_static_fields(self, client) -> None:
        response = client.get("/api/concepts")
        assert response.status_code == 200
        body = response.json()
        assert len(body["concepts"]) == 8  # conftest's fixture: concept_count=8
        first = body["concepts"][0]
        assert set(first) == {"id", "name", "tam", "medium", "categories", "flavor"}
        assert first["medium"] == ["digital"]
        assert first["categories"] == ["product"]


class TestRules:
    def test_returns_rules_text(self, client) -> None:
        response = client.get("/api/rules")
        assert response.status_code == 200
        assert "Product: The Game" in response.json()["text"]


class TestPortfolioBuffsAndRequired:
    def test_buffs_and_required_present_and_shaped(self, client) -> None:
        view = _new_game(client, ("alice", "bob"), seed=1)
        item = view["portfolio"][0]
        assert set(item["buffs"]) == {"D", "V", "F"}
        assert set(item["required"]) == {"D", "V", "F"}
        # discovery's base requirement (fixtures.make_board): D=3 V=2 F=1;
        # no skills held yet at turn 0, so buffs are all zero.
        assert item["required"] == {"D": 3, "V": 2, "F": 1}
        assert item["buffs"] == {"D": 0, "V": 0, "F": 0}


class TestHistory:
    def test_empty_on_create_and_on_plain_get(self, client) -> None:
        view = _new_game(client)
        assert view["history"] == []
        fetched = client.get(f"/api/games/{view['game_id']}").json()
        assert fetched["history"] == []

    def test_move_reports_landing_space_and_drawn_card(self, client) -> None:
        # fixtures' board: spaces = ["D","V","F","skills","chance"] * 3.
        # Every concept starts at offset 0, so a first roll (1-6) always
        # lands within the first 6 -- no gateway-wrap edge case here.
        view = _new_game(client, ("alice", "bob"), seed=5)
        roll = int(re.search(r"Rolled: (\d+)", view["observation"]).group(1))
        space_type = (["D", "V", "F", "skills", "chance"] * 3)[roll - 1]
        concept_name = view["portfolio"][0]["name"]  # matches option 0 (forward)

        result = client.post(f"/api/games/{view['game_id']}/actions", json={"action_index": 0})
        assert result.status_code == 200
        history = result.json()["history"]

        assert len(history) == 1
        entry = history[0]
        assert entry["turn"] == 0
        assert entry["at"]  # a non-empty ISO timestamp
        assert concept_name in entry["text"]
        if space_type in ("D", "V", "F"):
            assert SPACE_LABELS[space_type] in entry["text"] and "drew" in entry["text"]
        elif space_type == "chance":
            assert "Chance" in entry["text"] and "drew" in entry["text"]
        else:
            assert "Skills" in entry["text"]

    def test_survives_a_refetch_and_is_newest_first(self, client) -> None:
        view = _new_game(client, ("alice",), seed=5)
        game_id = view["game_id"]
        for _ in range(3):
            view = client.post(f"/api/games/{game_id}/actions", json={"action_index": 0}).json()

        refetched = client.get(f"/api/games/{game_id}").json()
        assert refetched["history"] == view["history"]
        assert len(refetched["history"]) == 3
        # newest first: the last turn's entry should be at index 0
        turns = [h["turn"] for h in refetched["history"]]
        assert turns == sorted(turns, reverse=True)
