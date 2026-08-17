"""
Intake router — web-form POST that runs the full classify -> route ->
persist pipeline end-to-end. Slack Events API webhook intake is stubbed for
Phase 3 (real Slack integration) and not wired up yet in v1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.jira_adapter import get_jira_adapter
from app.adapters.slack_adapter import get_slack_adapter
from app.db import get_session
from app.models import Classification as ClassificationModel
from app.models import Request as RequestModel
from app.models import RoutingDecision
from app.services import classification_service, routing_engine

router = APIRouter(prefix="/api/requests", tags=["requests"])


class IncomingRequest(BaseModel):
    requester: str
    text: str
    source: str = "web"


class RoutingResponse(BaseModel):
    request_id: int
    team: str
    confidence: float
    urgency: str
    reasoning: str
    status: str
    jira_ticket_key: str | None = None
    slack_message_ts: str | None = None
    assigned_oncall: str | None = None


@router.post("", response_model=RoutingResponse)
def submit_request(payload: IncomingRequest, db: Session = Depends(get_session)):
    req = RequestModel(source=payload.source, requester=payload.requester, raw_text=payload.text)
    db.add(req)
    db.commit()
    db.refresh(req)

    classification = classification_service.classify(payload.text)

    db.add(
        ClassificationModel(
            request_id=req.id,
            team=classification.team,
            confidence=classification.confidence,
            urgency=classification.urgency,
            reasoning=classification.reasoning,
            secondary_team=classification.secondary_team,
            model_version=classification.model_version,
        )
    )
    db.commit()

    result = routing_engine.route(
        db=db,
        request_text=payload.text,
        requester=payload.requester,
        classification=classification,
        slack_adapter=get_slack_adapter(),
        jira_adapter=get_jira_adapter(),
    )

    db.add(
        RoutingDecision(
            request_id=req.id,
            team=result.team,
            status=result.status,
            jira_ticket_key=result.jira_ticket_key,
            slack_message_ts=result.slack_message_ts,
            assigned_oncall=result.assigned_oncall,
        )
    )
    db.commit()

    return RoutingResponse(
        request_id=req.id,
        team=classification.team,
        confidence=classification.confidence,
        urgency=classification.urgency,
        reasoning=classification.reasoning,
        status=result.status,
        jira_ticket_key=result.jira_ticket_key,
        slack_message_ts=result.slack_message_ts,
        assigned_oncall=result.assigned_oncall,
    )


@router.get("")
def list_requests(limit: int = 50, db: Session = Depends(get_session)):
    reqs = db.query(RequestModel).order_by(RequestModel.id.desc()).limit(limit).all()
    out = []
    for r in reqs:
        classification = (
            db.query(ClassificationModel)
            .filter(ClassificationModel.request_id == r.id)
            .order_by(ClassificationModel.id.desc())
            .first()
        )
        decision = (
            db.query(RoutingDecision)
            .filter(RoutingDecision.request_id == r.id)
            .order_by(RoutingDecision.id.desc())
            .first()
        )
        out.append(
            {
                "id": r.id,
                "source": r.source,
                "requester": r.requester,
                "text": r.raw_text,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "team": classification.team if classification else None,
                "confidence": classification.confidence if classification else None,
                "urgency": classification.urgency if classification else None,
                "status": decision.status if decision else None,
                "jira_ticket_key": decision.jira_ticket_key if decision else None,
            }
        )
    return {"requests": out}
