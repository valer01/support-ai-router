"""Engine/session setup. SQLite by default (dev); override
SUPPORTROUTER_DATABASE_URL for Postgres later without touching callers."""
from __future__ import annotations
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

DATA_DIR = os.environ.get(
    "SUPPORTROUTER_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data"),
)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "app.db")
DATABASE_URL = os.environ.get("SUPPORTROUTER_DATABASE_URL", f"sqlite:///{DB_PATH}")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
