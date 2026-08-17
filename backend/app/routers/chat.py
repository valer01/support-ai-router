"""
Chat intake router — POST /api/chat drives a stateful, turn-by-turn
conversation (see app/services/chat_service.py) instead of the old
single-shot form POST. The frontend chat widget calls this once per user
message, carrying conversation_id after the first turn.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.jira_adapter import get_jira_adapter
from app.adapters.slack_adapter import get_slack_adapter
from app.db import get_session
from app.models import Classification as ClassificationModel
from app.models import Conversation, ConversationMessage
from app.models import Request as RequestModel
from app.models import RoutingDecision
from app.services import chat_service, routing_engine

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatTurnIn(BaseModel):
    conversation_id: int | None = None
    requester: str
    message: str


class ChatTurnOut(BaseModel):
    conversation_id: int
    message: str
    status: str  # in_progress | auto_routed | pending_review
    team: str | None = None
    confidence: float | None = None
    jira_ticket_key: str | None = None
    slack_message_ts: str | None = None
    assigned_oncall: str | None = None


@router.post("", response_model=ChatTurnOut)
def chat_turn(payload: ChatTurnIn, db: Session = Depends(get_session)):
    if payload.conversation_id is not None:
        conversation = db.get(Conversation, payload.conversation_id)
    else:
        conversation = None

    if conversation is None:
        conversation = Conversation(requester=payload.requester, status="in_progress")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(ConversationMessage(conversation_id=conversation.id, role="user", content=payload.message))
    db.commit()

    history = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.asc())
        .all()
    )
    transcript = [{"role": m.role, "content": m.content} for m in history]

    decision = chat_service.chat_turn(transcript, conversation.clarifying_questions_asked)

    db.add(ConversationMessage(conversation_id=conversation.id, role="assistant", content=decision.message))

    if decision.action == "ask":
        conversation.clarifying_questions_asked += 1
        db.commit()
        return ChatTurnOut(
            conversation_id=conversation.id,
            message=decision.message,
            status="in_progress",
        )

    # action == "route": combine every user message in this conversation as
    # the full request text (so classification/tickets see the whole
    # exchange, not just the first line).
    full_text = "\n".join(m.content for m in history if m.role == "user")

    req = RequestModel(
        source="web_chat",
        conversation_id=conversation.id,
        requester=payload.requester,
        raw_text=full_text,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    db.add(
        ClassificationModel(
            request_id=req.id,
            team=decision.team or "",
            confidence=decision.confidence or 0.0,
            urgency=decision.urgency or "medium",
            reasoning=decision.reasoning or "",
            secondary_team=decision.secondary_team,
            model_version=decision.model_version,
        )
    )
    db.commit()

    from app.services.classification_service import Classification as ClassificationDTO

    classification_dto = ClassificationDTO(
        team=decision.team or "",
        confidence=decision.confidence or 0.0,
        urgency=decision.urgency or "medium",
        reasoning=decision.reasoning or "",
        secondary_team=decision.secondary_team,
        model_version=decision.model_version,
    )

    result = routing_engine.route(
        db=db,
        request_text=full_text,
        requester=payload.requester,
        classification=classification_dto,
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
    conversation.status = result.status
    db.commit()

    reply = decision.message
    if result.status == routing_engine.STATUS_AUTO_ROUTED:
        reply += f"\n\nTicket {result.jira_ticket_key} created for {result.team} ({team_channel_hint(db, result.team)})."
        if result.assigned_oncall:
            reply += f" On-call: {result.assigned_oncall}."
    else:
        reply += "\n\nI'm not fully confident, so I've flagged this for a human to triage rather than guess wrong."

    return ChatTurnOut(
        conversation_id=conversation.id,
        message=reply,
        status=result.status,
        team=result.team,
        confidence=decision.confidence,
        jira_ticket_key=result.jira_ticket_key,
        slack_message_ts=result.slack_message_ts,
        assigned_oncall=result.assigned_oncall,
    )


def team_channel_hint(db: Session, team_name: str) -> str:
    from app.models import Team

    team = db.query(Team).filter(Team.name == team_name).first()
    return team.slack_channel if team else ""


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_session)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        return {"error": "not found"}
    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.id.asc())
        .all()
    )
    return {
        "conversation_id": conversation.id,
        "status": conversation.status,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
