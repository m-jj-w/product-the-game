"""Shared fixtures for server/app.py-backed tests (test_server.py,
test_cli.py): override both data dependencies with fakes so nothing
real -- neither the data/ dir's current content nor Firestore -- is
ever touched."""

from __future__ import annotations

import pytest

from server.app import app, get_game_data, get_game_store
from server.store import InMemoryGameStore
from tests.fixtures import make_game_data

SERVER_TEST_DATA = make_game_data(concept_count=8)


@pytest.fixture(autouse=True)
def _override_server_dependencies():
    # One store instance for the whole test, not one per call -- games
    # created early in a test must still be there for later requests,
    # exactly like the real singleton _STORE in server/app.py.
    store = InMemoryGameStore()
    app.dependency_overrides[get_game_data] = lambda: SERVER_TEST_DATA
    app.dependency_overrides[get_game_store] = lambda: store
    yield
    app.dependency_overrides.clear()
