"""
Jira adapter — Protocol + Mock (default) + Real (Jira REST API v3).
Same mode-selection pattern as slack_adapter.py.
"""
from __future__ import annotations
import itertools
import json
import os
import re
import threading
from typing import Protocol

_DATA_DIR = os.environ.get(
    "SUPPORTROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)
_MOCK_LOG_PATH = os.path.join(_DATA_DIR, "mock_jira_log.jsonl")
_LOCK = threading.Lock()

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "to", "of",
    "in", "on", "for", "and", "or", "it", "this", "that", "my", "our", "with",
    "not", "no", "at", "i", "we", "you", "your", "just", "can", "cant",
    "won't", "wont", "doesn't", "doesnt", "isn't", "isnt",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


class JiraAdapterProtocol(Protocol):
    def create_ticket(self, project_key: str, summary: str, description: str, labels: list[str] | None = None) -> str:
        """Returns the created ticket key, e.g. 'ITSUP-1042'."""
        ...

    def get_ticket(self, key: str) -> dict:
        ...

    def search_similar_tickets(self, query_text: str, limit: int = 5) -> list[dict]:
        """Returns up to `limit` past tickets that look textually similar to
        query_text, most-similar first. Each item is a COMPACT dict —
        {key, summary, project_key} — deliberately not the full ticket body,
        to keep this cheap to feed into an LLM prompt. Never raises on "no
        results found"; returns []. Real callers should still be prepared
        to catch network/auth errors."""
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

    def search_similar_tickets(self, query_text: str, limit: int = 5) -> list[dict]:
        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []
        scored = []
        for ticket in self._tickets.values():
            ticket_tokens = _tokenize(ticket["summary"]) | _tokenize(ticket.get("description", ""))
            overlap = len(query_tokens & ticket_tokens)
            if overlap > 0:
                scored.append((overlap, ticket))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {"key": t["key"], "summary": t["summary"], "project_key": t["project_key"]}
            for _, t in scored[:limit]
        ]


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

    def search_similar_tickets(self, query_text: str, limit: int = 5) -> list[dict]:
        import httpx

        # Keep the JQL free-text term short and safe: strip quotes, cap
        # length. Jira's `text ~` operator does its own fuzzy/stemmed
        # matching server-side, so we don't need to be clever here -- just
        # avoid sending something that breaks JQL syntax.
        safe_query = query_text.replace('"', "'").strip()[:200]
        if not safe_query:
            return []
        jql = f'text ~ "{safe_query}" ORDER BY updated DESC'

        resp = httpx.get(
            f"{self.base_url}/rest/api/3/search",
            auth=(self.email, self.api_token),
            params={"jql": jql, "maxResults": limit, "fields": "summary,project"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "key": issue["key"],
                "summary": issue.get("fields", {}).get("summary", ""),
                "project_key": issue.get("fields", {}).get("project", {}).get("key", ""),
            }
            for issue in data.get("issues", [])[:limit]
        ]


_singleton_mock = MockJiraAdapter()


def get_jira_adapter() -> JiraAdapterProtocol:
    mode = os.environ.get("SUPPORTROUTER_JIRA_MODE", "mock").lower()
    if mode == "real":
        return RealJiraAdapter()
    return _singleton_mock
