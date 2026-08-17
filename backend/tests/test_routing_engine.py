"""Unit tests for routing_engine.route() confidence gating, per Task 1.5.
Relies on tests/conftest.py having fixed the test DB path before app.db is
first imported."""
from unittest.mock import MagicMock

import pytest

from app.db import SessionLocal, init_db
from app.models import Team
from app.services import routing_engine
from app.services.classification_service import Classification


@pytest.fixture()
def db_session():
    init_db()
    session = SessionLocal()
    existing = session.query(Team).filter(Team.name == "IT").first()
    if not existing:
        session.add(
            Team(
                name="IT",
                slack_channel="#it-support",
                jira_project_key="ITSUP",
                ownership_description="test",
            )
        )
        session.commit()
    yield session
    session.close()


def test_high_confidence_routes_and_calls_adapters(db_session):
    classification = Classification(
        team="IT", confidence=0.9, urgency="medium", reasoning="clear IT issue"
    )
    slack = MagicMock()
    slack.post_message.return_value = "1234.5678"
    jira = MagicMock()
    jira.create_ticket.return_value = "ITSUP-1001"

    result = routing_engine.route(
        db=db_session,
        request_text="Can't connect to VPN",
        requester="alice",
        classification=classification,
        slack_adapter=slack,
        jira_adapter=jira,
    )

    assert result.status == routing_engine.STATUS_AUTO_ROUTED
    assert result.team == "IT"
    assert result.jira_ticket_key == "ITSUP-1001"
    slack.post_message.assert_called_once()
    jira.create_ticket.assert_called_once()


def test_low_confidence_routes_to_pending_review_without_adapter_calls(db_session):
    classification = Classification(
        team="IT", confidence=0.4, urgency="low", reasoning="ambiguous"
    )
    slack = MagicMock()
    jira = MagicMock()

    result = routing_engine.route(
        db=db_session,
        request_text="something vague",
        requester="bob",
        classification=classification,
        slack_adapter=slack,
        jira_adapter=jira,
    )

    assert result.status == routing_engine.STATUS_PENDING_REVIEW
    slack.post_message.assert_not_called()
    jira.create_ticket.assert_not_called()


def test_unknown_team_routes_to_pending_review(db_session):
    classification = Classification(
        team="NotARealTeam", confidence=0.95, urgency="medium", reasoning="oops"
    )
    slack = MagicMock()
    jira = MagicMock()

    result = routing_engine.route(
        db=db_session,
        request_text="whatever",
        requester="carol",
        classification=classification,
        slack_adapter=slack,
        jira_adapter=jira,
    )

    assert result.status == routing_engine.STATUS_PENDING_REVIEW
    slack.post_message.assert_not_called()
    jira.create_ticket.assert_not_called()
