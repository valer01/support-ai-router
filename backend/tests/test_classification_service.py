"""Unit tests for classification_service.classify() using a mocked httpx
call — no live API access, per Task 1.3 in the plan."""
import json
from unittest.mock import patch, MagicMock

from app.services import classification_service


def _mock_anthropic_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "content": [{"type": "text", "text": json.dumps(payload)}],
    }
    return resp


def test_classify_returns_expected_team_for_clear_it_request():
    payload = {
        "team": "IT",
        "confidence": 0.95,
        "urgency": "medium",
        "reasoning": "VPN connectivity issue for an individual user.",
        "secondary_team": None,
    }
    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_anthropic_response(payload)):
        result = classification_service.classify("Can't connect to VPN")

    assert result.team == "IT"
    assert result.confidence >= 0.7
    assert result.urgency == "medium"


def test_classify_falls_back_when_no_api_key():
    with patch.object(classification_service, "ANTHROPIC_API_KEY", None):
        result = classification_service.classify("Can't connect to VPN")

    assert result.confidence == 0.0
    assert "LLM unavailable" in result.reasoning


def test_classify_retries_once_then_falls_back_on_unparseable_json():
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.raise_for_status = MagicMock()
    bad_resp.json.return_value = {"content": [{"type": "text", "text": "not json at all"}]}

    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=bad_resp):
        result = classification_service.classify("some ambiguous request")

    assert result.confidence == 0.0
    assert "unparseable" in result.reasoning.lower() or "LLM unavailable" in result.reasoning


def test_classify_caps_confidence_for_unknown_team_name():
    payload = {
        "team": "Marketing",  # not a real team
        "confidence": 0.9,
        "urgency": "low",
        "reasoning": "guessed",
        "secondary_team": None,
    }
    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_anthropic_response(payload)):
        result = classification_service.classify("something unrelated")

    assert result.confidence <= 0.3
