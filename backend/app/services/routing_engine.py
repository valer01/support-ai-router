"""
Routing engine — confidence-gated dispatch to adapters.

route() takes a Classification (from classification_service.classify) and,
if confidence is above the threshold, calls the Slack + Jira adapters and
looks up on-call, returning an "auto_routed" RoutingDecision. Below
threshold, it returns "pending_review" and makes NO adapter calls at all
(see plan §3 rule 3 — a wrong ticket/notification is worse than a short
delay for human triage).
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.adapters.jira_adapter import JiraAdapterProtocol
from app.adapters.oncall_adapter import current_oncall
from app.adapters.slack_adapter import SlackAdapterProtocol
from app.models import Team
from app.services.classification_service import Classification
from app.services import audit

CONFIDENCE_THRESHOLD = float(os.environ.get("SUPPORTROUTER_CONFIDENCE_THRESHOLD", "0.7"))

STATUS_AUTO_ROUTED = "auto_routed"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_HUMAN_ROUTED = "human_routed"


@dataclass
class RoutingResult:
    status: str
    team: str
    jira_ticket_key: Optional[str] = None
    slack_message_ts: Optional[str] = None
    assigned_oncall: Optional[str] = None


def route(
    db: Session,
    request_text: str,
    requester: str,
    classification: Classification,
    slack_adapter: SlackAdapterProtocol,
    jira_adapter: JiraAdapterProtocol,
    confidence_threshold: float | None = None,
) -> RoutingResult:
    threshold = CONFIDENCE_THRESHOLD if confidence_threshold is None else confidence_threshold

    if classification.confidence < threshold:
        audit.record(
            action="route_pending_review",
            actor=requester,
            detail={
                "team_guess": classification.team,
                "confidence": classification.confidence,
                "reasoning": classification.reasoning,
            },
        )
        return RoutingResult(status=STATUS_PENDING_REVIEW, team=classification.team)

    team = db.query(Team).filter(Team.name == classification.team).first()
    if team is None:
        # Defensive: classifier returned a team name that isn't seeded.
        audit.record(
            action="route_pending_review",
            actor=requester,
            detail={"team_guess": classification.team, "reason": "unknown team, not seeded"},
        )
        return RoutingResult(status=STATUS_PENDING_REVIEW, team=classification.team)

    oncall = current_oncall(db, team.name)
    slack_text = (
        f"[Support AI Router] New {classification.urgency.upper()} priority request "
        f"from {requester}:\n> {request_text}\n"
        f"Confidence: {classification.confidence:.2f} · {classification.reasoning}"
    )
    if oncall:
        slack_text += f"\nOn-call: {oncall}"
    slack_ts = slack_adapter.post_message(team.slack_channel, slack_text)

    ticket_key = jira_adapter.create_ticket(
        project_key=team.jira_project_key,
        summary=request_text[:200],
        description=(
            f"Auto-routed by Support AI Router.\n\n"
            f"Requester: {requester}\n"
            f"Confidence: {classification.confidence:.2f}\n"
            f"Urgency: {classification.urgency}\n"
            f"Reasoning: {classification.reasoning}\n\n"
            f"Original request:\n{request_text}"
        ),
        labels=["support-ai-router", classification.urgency],
    )

    audit.record(
        action="route_auto_routed",
        actor=requester,
        detail={
            "team": team.name,
            "confidence": classification.confidence,
            "jira_ticket_key": ticket_key,
            "slack_message_ts": slack_ts,
            "assigned_oncall": oncall,
        },
    )

    return RoutingResult(
        status=STATUS_AUTO_ROUTED,
        team=team.name,
        jira_ticket_key=ticket_key,
        slack_message_ts=slack_ts,
        assigned_oncall=oncall,
    )
