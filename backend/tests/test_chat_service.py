"""Unit tests for chat_service.chat_turn() — clarifying-question budget,
ask vs route actions, fallback behavior."""
import json
from unittest.mock import patch, MagicMock

from app.services import chat_service


def _mock_response(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"content": [{"type": "text", "text": json.dumps(payload)}]}
    return resp


def test_chat_turn_routes_immediately_for_clear_request():
    payload = {
        "action": "route",
        "message": "Got it — routing this to IT.",
        "team": "IT",
        "confidence": 0.93,
        "urgency": "medium",
        "reasoning": "Clear VPN connectivity issue.",
        "secondary_team": None,
    }
    transcript = [{"role": "user", "content": "Can't connect to VPN"}]
    with patch.object(chat_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_response(payload)):
        decision = chat_service.chat_turn(transcript, questions_asked_so_far=0)

    assert decision.action == "route"
    assert decision.team == "IT"
    assert decision.confidence == 0.93


def test_chat_turn_asks_clarifying_question_when_ambiguous():
    payload = {
        "action": "ask",
        "message": "Is this affecting just you, or the whole team?",
        "team": None,
        "confidence": None,
        "urgency": None,
        "reasoning": None,
        "secondary_team": None,
    }
    transcript = [{"role": "user", "content": "Something is broken"}]
    with patch.object(chat_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_response(payload)):
        decision = chat_service.chat_turn(transcript, questions_asked_so_far=0)

    assert decision.action == "ask"
    assert "?" in decision.message


def test_chat_turn_forces_route_after_question_budget_exhausted():
    # Model tries to ask again even though budget is exhausted -- server
    # must override to "route" regardless.
    payload = {
        "action": "ask",
        "message": "Can you tell me more?",
        "team": None,
        "confidence": None,
        "urgency": None,
        "reasoning": None,
        "secondary_team": None,
    }
    transcript = [{"role": "user", "content": "still vague"}]
    with patch.object(chat_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch.object(chat_service, "MAX_CLARIFYING_QUESTIONS", 2), \
         patch("httpx.post", return_value=_mock_response(payload)):
        decision = chat_service.chat_turn(transcript, questions_asked_so_far=2)

    assert decision.action == "route"
    assert decision.confidence == 0.0


def test_chat_turn_falls_back_when_no_api_key():
    transcript = [{"role": "user", "content": "help"}]
    with patch.object(chat_service, "ANTHROPIC_API_KEY", None):
        decision = chat_service.chat_turn(transcript, questions_asked_so_far=0)

    assert decision.action == "route"
    assert decision.confidence == 0.0
    assert "LLM unavailable" in decision.reasoning
