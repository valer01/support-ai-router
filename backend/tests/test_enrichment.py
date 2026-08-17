"""Tests that classify()/chat_turn() correctly gate the enrichment
(similar-past-tickets) second pass on confidence, and never call it when
confidence is already high -- the whole point of the token-saving design."""
import json
from unittest.mock import MagicMock, patch

from app.services import classification_service, chat_service


def _mock_response(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"content": [{"type": "text", "text": json.dumps(payload)}]}
    return resp


def test_classify_skips_enrichment_when_confident():
    high_conf_payload = {
        "team": "IT",
        "confidence": 0.95,
        "urgency": "medium",
        "reasoning": "clear",
        "secondary_team": None,
    }
    fake_jira = MagicMock()

    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_response(high_conf_payload)) as mock_post:
        result = classification_service.classify("Can't connect to VPN", jira_adapter=fake_jira)

    assert result.confidence == 0.95
    fake_jira.search_similar_tickets.assert_not_called()
    # Only ONE Claude call made -- no enrichment round trip.
    assert mock_post.call_count == 1


def test_classify_enriches_when_uncertain_and_history_available():
    uncertain_payload = {
        "team": "IT",
        "confidence": 0.6,
        "urgency": "low",
        "reasoning": "somewhat ambiguous",
        "secondary_team": None,
    }
    enriched_payload = {
        "team": "IT",
        "confidence": 0.88,
        "urgency": "low",
        "reasoning": "matches a past resolved IT ticket",
        "secondary_team": None,
    }
    fake_jira = MagicMock()
    fake_jira.search_similar_tickets.return_value = [
        {"key": "ITSUP-842", "summary": "Can't reach VPN from home", "project_key": "ITSUP"},
    ]

    responses = [_mock_response(uncertain_payload), _mock_response(enriched_payload)]
    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", side_effect=responses) as mock_post:
        result = classification_service.classify("something vague about vpn", jira_adapter=fake_jira)

    assert mock_post.call_count == 2
    fake_jira.search_similar_tickets.assert_called_once()
    assert result.confidence == 0.88
    assert "enriched with past-ticket history" in result.reasoning


def test_classify_does_not_enrich_on_hard_failure_zero_confidence():
    fake_jira = MagicMock()
    with patch.object(classification_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", return_value=_mock_response({"not": "valid schema"})):
        result = classification_service.classify("whatever", jira_adapter=fake_jira)

    assert result.confidence == 0.0
    fake_jira.search_similar_tickets.assert_not_called()


def test_chat_turn_enriches_uncertain_route_decision():
    uncertain_payload = {
        "action": "route",
        "message": "Routing to IT.",
        "team": "IT",
        "confidence": 0.6,
        "urgency": "low",
        "reasoning": "somewhat ambiguous",
        "secondary_team": None,
    }
    enriched_payload = {
        "action": "route",
        "message": "Routing to IT, confirmed by similar past tickets.",
        "team": "IT",
        "confidence": 0.9,
        "urgency": "low",
        "reasoning": "matches history",
        "secondary_team": None,
    }
    fake_jira = MagicMock()
    fake_jira.search_similar_tickets.return_value = [
        {"key": "ITSUP-842", "summary": "Can't reach VPN from home", "project_key": "ITSUP"},
    ]
    transcript = [{"role": "user", "content": "something vague about vpn"}]

    responses = [_mock_response(uncertain_payload), _mock_response(enriched_payload)]
    with patch.object(chat_service, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("httpx.post", side_effect=responses) as mock_post:
        decision = chat_service.chat_turn(transcript, questions_asked_so_far=0, jira_adapter=fake_jira)

    assert mock_post.call_count == 2
    assert decision.confidence == 0.9
    assert "enriched with past-ticket history" in decision.reasoning
