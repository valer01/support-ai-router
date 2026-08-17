"""
On-call adapter — v1 is a StoredRotationAdapter reading the OnCallEntry
table (this IS the real source of truth for v1, no mock/real split needed
until a PagerDuty/Opsgenie integration is added later — see plan §4.3).
"""
from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import OnCallEntry, Team


def current_oncall(db: Session, team_name: str) -> str | None:
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        return None
    now = datetime.now(timezone.utc)
    entry = (
        db.query(OnCallEntry)
        .filter(OnCallEntry.team_id == team.id)
        .filter(OnCallEntry.start_at <= now)
        .filter(OnCallEntry.end_at >= now)
        .order_by(OnCallEntry.start_at.desc())
        .first()
    )
    return entry.person_name if entry else None
