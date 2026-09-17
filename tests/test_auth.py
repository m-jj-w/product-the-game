"""Tests for server/auth.py: the optional shared-passphrase gate."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from server.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _basic_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class TestNoPasswordConfigured:
    def test_requests_pass_through_unauthenticated(self, client, monkeypatch) -> None:
        monkeypatch.delenv("AUTH_PASSWORD", raising=False)
        response = client.get("/")
        assert response.status_code == 200


class TestPasswordConfigured:
    def test_missing_credentials_are_rejected(self, client, monkeypatch) -> None:
        monkeypatch.setenv("AUTH_PASSWORD", "secret")
        response = client.get("/")
        assert response.status_code == 401
        assert "Basic" in response.headers["www-authenticate"]

    def test_wrong_credentials_are_rejected(self, client, monkeypatch) -> None:
        monkeypatch.setenv("AUTH_PASSWORD", "secret")
        response = client.get("/", headers=_basic_header("play", "not-it"))
        assert response.status_code == 401

    def test_correct_credentials_pass_through(self, client, monkeypatch) -> None:
        monkeypatch.setenv("AUTH_PASSWORD", "secret")
        response = client.get("/", headers=_basic_header("play", "secret"))
        assert response.status_code == 200

    def test_custom_username_is_honored(self, client, monkeypatch) -> None:
        monkeypatch.setenv("AUTH_PASSWORD", "secret")
        monkeypatch.setenv("AUTH_USERNAME", "admin")
        assert client.get("/", headers=_basic_header("play", "secret")).status_code == 401
        assert client.get("/", headers=_basic_header("admin", "secret")).status_code == 200

    def test_gate_covers_the_api_too(self, client, monkeypatch) -> None:
        monkeypatch.setenv("AUTH_PASSWORD", "secret")
        response = client.post("/games", json={"player_ids": ["alice"]})
        assert response.status_code == 401
