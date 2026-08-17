from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.oncall_adapter import current_oncall
from app.db import get_session
from app.models import OnCallEntry, Team

router = APIRouter(prefix="/api/oncall", tags=["oncall"])


class OnCallEntryIn(BaseModel):
    team_name: str
    person_name: str
    person_slack_id: str | None = None
    start_at: datetime
    end_at: datetime


@router.get("")
def list_current_oncall(db: Session = Depends(get_session)):
    teams = db.query(Team).order_by(Team.name).all()
    return {"oncall": [{"team": t.name, "person": current_oncall(db, t.name)} for t in teams]}


@router.post("")
def add_oncall_entry(payload: OnCallEntryIn, db: Session = Depends(get_session)):
    team = db.query(Team).filter(Team.name == payload.team_name).first()
    if not team:
        return {"error": f"unknown team '{payload.team_name}'"}
    entry = OnCallEntry(
        team_id=team.id,
        person_name=payload.person_name,
        person_slack_id=payload.person_slack_id,
        start_at=payload.start_at.astimezone(timezone.utc).replace(tzinfo=None),
        end_at=payload.end_at.astimezone(timezone.utc).replace(tzinfo=None),
    )
    db.add(entry)
    db.commit()
    return {"id": entry.id}
