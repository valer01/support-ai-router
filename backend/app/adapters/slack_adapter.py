"""
Slack adapter — Protocol + Mock (default) + Real (Slack Web API).

Mode selection is per-process via SUPPORTROUTER_SLACK_MODE env var
("mock" default, "real" requires SLACK_BOT_TOKEN). This mirrors
ask-devops-dashboard's adapters.py dispatch pattern, but keeps mock and
real adapters both present (support-ai-router's mock mode is a first-class,
permanent dev/test path — unlike ask-devops-dashboard, which later removed
mock mode once real infra was always available).
"""
from __future__ import annotations
import json
import os
import threading
import time
from typing import Protocol

_DATA_DIR = os.environ.get(
    "SUPPORTROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)
_MOCK_LOG_PATH = os.path.join(_DATA_DIR, "mock_slack_log.jsonl")
_LOCK = threading.Lock()


class SlackAdapterProtocol(Protocol):
    def post_message(self, channel: str, text: str) -> str:
        """Posts a message, returns a message timestamp/id."""
        ...

    def lookup_user(self, user_id: str) -> dict:
        ...


class MockSlackAdapter:
    """In-memory + JSONL-logged, no network calls."""

    def __init__(self):
        self._sent: list[dict] = []

    def post_message(self, channel: str, text: str) -> str:
        ts = f"{time.time():.6f}"
        entry = {"channel": channel, "text": text, "ts": ts}
        self._sent.append(entry)
        os.makedirs(_DATA_DIR, exist_ok=True)
        with _LOCK:
            with open(_MOCK_LOG_PATH, "a") as f:
                f.write(json.dumps(entry) + "\n")
        return ts

    def lookup_user(self, user_id: str) -> dict:
        return {"id": user_id, "name": user_id, "mock": True}

    def sent_messages(self) -> list[dict]:
        return list(self._sent)


class RealSlackAdapter:
    """Live Slack Web API (chat.postMessage). Inbound events (Events
    API/Bolt) are handled separately in routers/intake.py — this class only
    covers outbound posting + user lookups needed by the routing engine."""

    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        if not self.bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN is required for RealSlackAdapter")

    def post_message(self, channel: str, text: str) -> str:
        import httpx

        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {self.bot_token}"},
            json={"channel": channel, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error')}")
        return data.get("ts", "")

    def lookup_user(self, user_id: str) -> dict:
        import httpx

        resp = httpx.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {self.bot_token}"},
            params={"user": user_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error')}")
        return data.get("user", {})


_singleton_mock = MockSlackAdapter()


def get_slack_adapter() -> SlackAdapterProtocol:
    mode = os.environ.get("SUPPORTROUTER_SLACK_MODE", "mock").lower()
    if mode == "real":
        return RealSlackAdapter()
    return _singleton_mock
