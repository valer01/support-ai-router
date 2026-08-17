"""Append-only JSON-lines audit log, same pattern as ask-devops-dashboard's
app/services/audit.py."""
from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timezone

_LOCK = threading.Lock()
_DATA_DIR = os.environ.get(
    "SUPPORTROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)
_LOG_PATH = os.path.join(_DATA_DIR, "audit_log.jsonl")


def _ensure_dir():
    os.makedirs(_DATA_DIR, exist_ok=True)


def record(action: str, actor: str, detail: dict) -> dict:
    _ensure_dir()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor,
        "detail": detail,
    }
    with _LOCK:
        with open(_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


def tail(n: int = 100) -> list[dict]:
    _ensure_dir()
    if not os.path.exists(_LOG_PATH):
        return []
    with open(_LOG_PATH) as f:
        lines = f.readlines()
    out = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return list(reversed(out))
