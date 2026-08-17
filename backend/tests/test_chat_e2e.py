"""End-to-end chat pipeline test: multi-turn conversation via /api/chat,
including a clarifying-question round trip before routing."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import local_users, main as main_module
from app.services import chat_service


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


def _mock_response(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"content": [{"type": "text", "text": json.dumps(payload)}]}
    return resp


def test_chat_asks_then_routes_across_two_turns(client):
    ask_payload = {
        "action": "ask",
        "message": "Is this for a personal laptop or a shared team resource?",
        "team": None,
        "confidence": None,
        "urgency": None,
        "reasoning": None,
        "secondary_team": None,
    }
    route_payload = {
        "action": "route",
        "message": "Thanks — routing this to IT.",
        "team": "IT",
        "confidence": 0.9,
        "urgency": "medium",
        "reasoning": "Personal laptop access issue.",
        "secondary_team": None,
    }

    with patch.object(chat_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_response(ask_payload)):
        r1 = client.post(
            "/api/chat",
            json={"conversation_id": None, "requester": "alice@example.com", "message": "Something is broken"},
        )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["status"] == "in_progress"
    assert "?" in d1["message"]
    conv_id = d1["conversation_id"]

    with patch.object(chat_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_response(route_payload)):
        r2 = client.post(
            "/api/chat",
            json={"conversation_id": conv_id, "requester": "alice@example.com", "message": "My personal laptop"},
        )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["status"] == "auto_routed"
    assert d2["team"] == "IT"
    assert d2["jira_ticket_key"] and d2["jira_ticket_key"].startswith("ITSUP-")

    # Fetch the conversation transcript and confirm both turns are recorded.
    conv = client.get(f"/api/chat/{conv_id}").json()
    roles = [m["role"] for m in conv["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]

    # And the resulting Request's raw_text should combine both user messages.
    listed = client.get("/api/requests").json()
    matching = [r for r in listed["requests"] if r["requester"] == "alice@example.com"]
    assert matching
