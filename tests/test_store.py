"""Tests for server/store.py: InMemoryGameStore and replay_with_history().

FirestoreGameStore itself is untested here -- it's a thin wrapper over
the real Firestore client, exercised by an actual deployment instead.
"""

from __future__ import annotations

from engine.engine import NewGameConfig, apply, legal_actions, new_game
from server.store import GameRecord, InMemoryGameStore, replay_with_history
from tests.fixtures import make_game_data

DATA = make_game_data(concept_count=8)


class TestInMemoryGameStore:
    def test_round_trips_a_record(self) -> None:
        store = InMemoryGameStore()
        record = GameRecord(
            player_ids=["alice", "bob"],
            seed=5,
            action_indices=[0, 2],
            action_timestamps=["t0", "t1"],
        )
        store.save("game-1", record)
        assert store.load("game-1") == record

    def test_unknown_id_returns_none(self) -> None:
        store = InMemoryGameStore()
        assert store.load("nope") is None

    def test_saving_again_overwrites(self) -> None:
        store = InMemoryGameStore()
        store.save("game-1", GameRecord(player_ids=["alice"], seed=1))
        store.save(
            "game-1",
            GameRecord(player_ids=["alice"], seed=1, action_indices=[0], action_timestamps=["t0"]),
        )
        assert store.load("game-1").action_indices == [0]


class TestReplayWithHistory:
    def test_no_actions_matches_a_fresh_new_game_and_empty_history(self) -> None:
        record = GameRecord(player_ids=["alice", "bob"], seed=7)
        replayed, history = replay_with_history(DATA, record)
        fresh = new_game(NewGameConfig(data=DATA, player_ids=["alice", "bob"]), 7)
        assert replayed == fresh
        assert history == []

    def test_replaying_stored_indices_matches_live_play(self) -> None:
        # Play three real steps live, recording which index was chosen
        # each time exactly as server/app.py's choose_action() does.
        state = new_game(NewGameConfig(data=DATA, player_ids=["alice", "bob"]), 3)
        chosen_indices = []
        for _ in range(3):
            actions = legal_actions(state)
            index = 0
            chosen_indices.append(index)
            state = apply(state, actions[index])

        timestamps = [f"t{i}" for i in range(3)]
        record = GameRecord(
            player_ids=["alice", "bob"],
            seed=3,
            action_indices=chosen_indices,
            action_timestamps=timestamps,
        )
        replayed, history = replay_with_history(DATA, record)

        assert replayed == state
        assert [h.at for h in history] == timestamps
        assert all(h.text for h in history)  # every step got some narration
