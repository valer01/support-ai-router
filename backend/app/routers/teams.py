from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Team

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("")
def list_teams(db: Session = Depends(get_session)):
    teams = db.query(Team).order_by(Team.name).all()
    return {
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "slack_channel": t.slack_channel,
                "jira_project_key": t.jira_project_key,
                "ownership_description": t.ownership_description,
            }
            for t in teams
        ]
    }
