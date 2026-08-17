"""SQLAlchemy models — see plan §4.2 for the full data-model rationale."""
from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    slack_channel: Mapped[str] = mapped_column(String(100))
    jira_project_key: Mapped[str] = mapped_column(String(20))
    ownership_description: Mapped[str] = mapped_column(Text)


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # slack | web | jira
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requester: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    team: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float)
    urgency: Mapped[str] = mapped_column(String(20))
    reasoning: Mapped[str] = mapped_column(Text)
    secondary_team: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    team: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))  # auto_routed | human_routed | pending_review
    jira_ticket_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_message_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_oncall: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OnCallEntry(Base):
    __tablename__ = "oncall_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    person_name: Mapped[str] = mapped_column(String(200))
    person_slack_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    corrected_team: Mapped[str] = mapped_column(String(50))
    corrected_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
