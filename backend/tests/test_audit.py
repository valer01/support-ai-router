"""Audit logging test, per Task 1.8. Relies on tests/conftest.py having
fixed SUPPORTROUTER_DATA_DIR before app.services.audit is first imported."""
import json
import os

from app.services import audit


def test_record_and_tail_audit_entries():
    entry = audit.record("route_auto_routed", "alice", {"team": "IT"})
    assert entry["action"] == "route_auto_routed"

    tailed = audit.tail(10)
    assert tailed[0]["actor"] == "alice"
    assert tailed[0]["detail"]["team"] == "IT"

    data_dir = os.environ["SUPPORTROUTER_DATA_DIR"]
    log_path = os.path.join(data_dir, "audit_log.jsonl")
    assert os.path.exists(log_path)
