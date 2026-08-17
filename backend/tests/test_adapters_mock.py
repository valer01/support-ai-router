"""Unit tests for mock Slack/Jira adapters, per Task 1.6. Relies on
tests/conftest.py having fixed SUPPORTROUTER_DATA_DIR before these adapter
modules are first imported."""
import json
import os

from app.adapters.slack_adapter import MockSlackAdapter
from app.adapters.jira_adapter import MockJiraAdapter


def test_mock_slack_adapter_logs_to_jsonl():
    adapter = MockSlackAdapter()
    ts = adapter.post_message("#it-support", "test message")

    assert ts
    data_dir = os.environ["SUPPORTROUTER_DATA_DIR"]
    log_path = os.path.join(data_dir, "mock_slack_log.jsonl")
    assert os.path.exists(log_path)
    with open(log_path) as f:
        lines = f.read().strip().split("\n")
    entry = json.loads(lines[-1])
    assert entry["channel"] == "#it-support"
    assert entry["text"] == "test message"


def test_mock_jira_adapter_generates_sequential_keys_per_project():
    adapter = MockJiraAdapter()
    key1 = adapter.create_ticket("ITSUP", "issue 1", "desc")
    key2 = adapter.create_ticket("ITSUP", "issue 2", "desc")
    key3 = adapter.create_ticket("DEVOPS", "issue 3", "desc")

    assert key1.startswith("ITSUP-")
    assert key2.startswith("ITSUP-")
    assert key1 != key2
    assert key3.startswith("DEVOPS-")
