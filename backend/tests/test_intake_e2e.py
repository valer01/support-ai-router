"""End-to-end integration test: POST /api/requests -> classify -> route ->
persist, per Task 1.7. Uses a mocked Claude response so it runs without
network access; the golden-set accuracy test covers real-API behavior.

Relies on tests/conftest.py to have already fixed SUPPORTROUTER_DATA_DIR /
SUPPORTROUTER_DATABASE_URL / SUPPORTROUTER_SESSION_SECRET before app.main
(and everything it imports) is first loaded, so no importlib.reload()
gymnastics are needed here."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import local_users, main as main_module
from app.services import classification_service


@pytest.fixture()
def client():
    with TestClient(main_module.app) as c:
        seeded_password = local_users.seed_default_user_if_missing()
        if seeded_password is None:
            local_users.set_password("test.admin", "TestPassw0rd!", name="Test Admin")
            seeded_password = "TestPassw0rd!"
        login = c.post(
            "/auth/local-login",
            data={"username": "test.admin", "password": seeded_password},
        )
        assert login.status_code in (200, 303)
        yield c


def _mock_anthropic_response(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"content": [{"type": "text", "text": json.dumps(payload)}]}
    return resp


def test_full_pipeline_routes_it_request_end_to_end(client):
    payload = {
        "team": "IT",
        "confidence": 0.92,
        "urgency": "medium",
        "reasoning": "VPN issue for an individual.",
        "secondary_team": None,
    }
    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_anthropic_response(payload)):
        resp = client.post(
            "/api/requests",
            json={"requester": "alice@example.com", "text": "Can't connect to VPN", "source": "web"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["team"] == "IT"
    assert data["status"] == "auto_routed"
    assert data["jira_ticket_key"] and data["jira_ticket_key"].startswith("ITSUP-")

    listed = client.get("/api/requests").json()
    assert any(r["id"] == data["request_id"] for r in listed["requests"])
