"""
Classification service — calls the Anthropic Messages API directly over
HTTPS (plain httpx, matching ask-devops-dashboard's claude_service.py
pattern; no SDK dependency).

classify() returns a Classification pydantic model with team/confidence/
urgency/reasoning/secondary_team. On any failure (no API key, HTTP error,
timeout, unparseable JSON after one retry) it returns a LOW-CONFIDENCE
fallback classification pointing at human review rather than raising or
silently guessing — see routing_engine.py for how confidence gates action.
"""
from __future__ import annotations
import json
import os
import re
from typing import Optional

import httpx
from pydantic import BaseModel, ValidationError

from app.routing_matrix import TEAM_NAMES, build_system_prompt

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("SUPPORTROUTER_CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT_S = int(os.environ.get("SUPPORTROUTER_CLAUDE_TIMEOUT", "30"))
MAX_TOKENS = int(os.environ.get("SUPPORTROUTER_CLAUDE_MAX_TOKENS", "512"))

FALLBACK_TEAM = TEAM_NAMES[0]


class Classification(BaseModel):
    model_config = {"protected_namespaces": ()}

    team: str
    confidence: float
    urgency: str
    reasoning: str
    secondary_team: Optional[str] = None
    model_version: str = "fallback"


def available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _fallback(reasoning: str) -> Classification:
    return Classification(
        team=FALLBACK_TEAM,
        confidence=0.0,
        urgency="medium",
        reasoning=reasoning,
        secondary_team=None,
        model_version="fallback",
    )


def _extract_json(text: str) -> dict:
    """Claude is asked for raw JSON; be lenient about stray markdown fences
    or whitespace, but don't try to fix genuinely malformed JSON here — the
    caller retries once with a stricter instruction instead."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    return json.loads(text)


def _call_claude(system_prompt: str, user_text: str, strict: bool = False) -> str:
    prompt = user_text
    if strict:
        prompt = (
            "Return ONLY a single valid JSON object, with no prose, no "
            "markdown fences, and no explanation before or after it.\n\n"
            f"Request text: {user_text}"
        )
    resp = httpx.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def classify(request_text: str, teams: list[dict] | None = None) -> Classification:
    if not ANTHROPIC_API_KEY:
        return _fallback("[LLM unavailable — ANTHROPIC_API_KEY not set; routed to human review]")

    system_prompt = build_system_prompt(teams)

    for attempt, strict in enumerate([False, True]):
        try:
            raw_text = _call_claude(system_prompt, request_text, strict=strict)
            parsed = _extract_json(raw_text)
            parsed["model_version"] = ANTHROPIC_MODEL
            classification = Classification(**parsed)
            if classification.team not in TEAM_NAMES:
                # Model hallucinated an unknown team name — treat as low
                # confidence rather than trusting a team that doesn't exist.
                classification.confidence = min(classification.confidence, 0.3)
            return classification
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as e:
            if attempt == 1:
                return _fallback(
                    f"[LLM returned unparseable output after retry: {e}; routed to human review]"
                )
            continue
        except httpx.HTTPStatusError as e:
            return _fallback(f"[Claude API error, HTTP {e.response.status_code}; routed to human review]")
        except httpx.TimeoutException:
            return _fallback("[Claude API timed out; routed to human review]")
        except Exception as e:  # noqa: BLE001
            return _fallback(f"[Claude API call failed: {e}; routed to human review]")

    return _fallback("[Unexpected classification failure; routed to human review]")
