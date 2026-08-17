"""
Jira adapter — Protocol + Mock (default) + Real (Jira REST API v3).
Same mode-selection pattern as slack_adapter.py.
"""
from __future__ import annotations
import itertools
import json
import os
import threading
from typing import Protocol

_DATA_DIR = os.environ.get(
    "SUPPORTROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)
_MOCK_LOG_PATH = os.path.join(_DATA_DIR, "mock_jira_log.jsonl")
_LOCK = threading.Lock()


class JiraAdapterProtocol(Protocol):
    def create_ticket(self, project_key: str, summary: str, description: str, labels: list[str] | None = None) -> str:
        """Returns the created ticket key, e.g. 'ITSUP-1042'."""
        ...

    def get_ticket(self, key: str) -> dict:
        ...


class MockJiraAdapter:
    """In-memory + JSONL-logged, generates fake sequential ticket keys per
    project so a demo/dev run looks realistic without touching a real Jira
    instance."""

    def __init__(self):
        self._tickets: dict[str, dict] = {}
        self._counters: dict[str, itertools.count] = {}

    def _next_key(self, project_key: str) -> str:
        counter = self._counters.setdefault(project_key, itertools.count(1000))
        return f"{project_key}-{next(counter)}"

    def create_ticket(self, project_key: str, summary: str, description: str, labels: list[str] | None = None) -> str:
        key = self._next_key(project_key)
        ticket = {
            "key": key,
            "project_key": project_key,
            "summary": summary,
            "description": description,
            "labels": labels or [],
        }
        self._tickets[key] = ticket
        os.makedirs(_DATA_DIR, exist_ok=True)
        with _LOCK:
            with open(_MOCK_LOG_PATH, "a") as f:
                f.write(json.dumps(ticket) + "\n")
        return key

    def get_ticket(self, key: str) -> dict:
        return self._tickets.get(key, {})


class RealJiraAdapter:
    """Live Jira REST API v3 (basic auth: email + API token)."""

    def __init__(self, base_url: str | None = None, email: str | None = None, api_token: str | None = None):
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN")
        if not (self.base_url and self.email and self.api_token):
            raise RuntimeError("JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN are required for RealJiraAdapter")

    def create_ticket(self, project_key: str, summary: str, description: str, labels: list[str] | None = None) -> str:
        import httpx

        resp = httpx.post(
            f"{self.base_url}/rest/api/3/issue",
            auth=(self.email, self.api_token),
            json={
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                        ],
                    },
                    "labels": labels or [],
                    "issuetype": {"name": "Task"},
                }
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["key"]

    def get_ticket(self, key: str) -> dict:
        import httpx

        resp = httpx.get(
            f"{self.base_url}/rest/api/3/issue/{key}",
            auth=(self.email, self.api_token),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


_singleton_mock = MockJiraAdapter()


def get_jira_adapter() -> JiraAdapterProtocol:
    mode = os.environ.get("SUPPORTROUTER_JIRA_MODE", "mock").lower()
    if mode == "real":
        return RealJiraAdapter()
    return _singleton_mock
