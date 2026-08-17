"""Seeds the 4 teams from routing_matrix.TEAMS into the DB if missing.

Run standalone with: python -m app.seed
"""
from __future__ import annotations

from app.db import SessionLocal, init_db
from app.models import Team
from app.routing_matrix import TEAMS


def seed_teams_if_missing() -> int:
    """Returns the number of teams inserted (0 if already seeded)."""
    init_db()
    db = SessionLocal()
    inserted = 0
    try:
        existing_names = {name for (name,) in db.query(Team.name).all()}
        for t in TEAMS:
            if t["name"] in existing_names:
                continue
            db.add(
                Team(
                    name=t["name"],
                    slack_channel=t["slack_channel"],
                    jira_project_key=t["jira_project_key"],
                    ownership_description=t["ownership_description"],
                )
            )
            inserted += 1
        if inserted:
            db.commit()
    finally:
        db.close()
    return inserted


if __name__ == "__main__":
    n = seed_teams_if_missing()
    print(f"Seeded {n} new team(s).")
