"""Tests for server/store.py: InMemoryGameStore and the replay() helper.

FirestoreGameStore itself is untested here -- it's a thin wrapper over
the real Firestore client, exercised by an actual deployment instead.
"""

from __future__ import annotations

from engine.engine import NewGameConfig, apply, legal_actions, new_game
from server.store import GameRecord, InMemoryGameStore, replay
from tests.fixtures import make_game_data

DATA = make_game_data(concept_count=8)


class TestInMemoryGameStore:
    def test_round_trips_a_record(self) -> None:
        store = InMemoryGameStore()
        record = GameRecord(player_ids=["alice", "bob"], seed=5, action_indices=[0, 2])
        store.save("game-1", record)
        assert store.load("game-1") == record

    def test_unknown_id_returns_none(self) -> None:
        store = InMemoryGameStore()
        assert store.load("nope") is None

    def test_saving_again_overwrites(self) -> None:
        store = InMemoryGameStore()
        store.save("game-1", GameRecord(player_ids=["alice"], seed=1, action_indices=[]))
        store.save("game-1", GameRecord(player_ids=["alice"], seed=1, action_indices=[0]))
        assert store.load("game-1").action_indices == [0]


class TestReplay:
    def test_no_actions_matches_a_fresh_new_game(self) -> None:
        record = GameRecord(player_ids=["alice", "bob"], seed=7, action_indices=[])
        replayed = replay(DATA, record)
        fresh = new_game(NewGameConfig(data=DATA, player_ids=["alice", "bob"]), 7)
        assert replayed == fresh

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

        record = GameRecord(player_ids=["alice", "bob"], seed=3, action_indices=chosen_indices)
        replayed = replay(DATA, record)
        assert replayed == state
