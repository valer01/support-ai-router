"""
Chat service — conversational intake. Unlike classification_service.classify
(single-shot, one message -> one classification), this drives a bounded
back-and-forth: the model can ask up to MAX_CLARIFYING_QUESTIONS clarifying
questions before it commits to a routing decision. Built on the same
routing_matrix system prompt and the same Anthropic Messages API call
pattern (direct httpx, no SDK) as classification_service.

Each turn returns a ChatDecision:
  - action == "ask"   -> `message` is a clarifying question to show the user;
                         no routing has happened yet.
  - action == "route" -> `message` is a short confirmation to show the user;
                         team/confidence/urgency/reasoning/secondary_team are
                         populated and ready to hand to routing_engine.route().

On any failure (no API key, HTTP error, timeout, unparseable JSON after one
retry), returns an immediate "route" decision at confidence 0.0 so the
request still lands in the pending_review human queue rather than hanging
the conversation forever.
"""
from __future__ import annotations
import json
import os
import re
from typing import Optional

import httpx
from pydantic import BaseModel, ValidationError

from app.routing_matrix import TEAM_NAMES, build_system_prompt
from app.services import ticket_context

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("SUPPORTROUTER_CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT_S = int(os.environ.get("SUPPORTROUTER_CLAUDE_TIMEOUT", "30"))
MAX_TOKENS = int(os.environ.get("SUPPORTROUTER_CLAUDE_MAX_TOKENS", "512"))

# Hard cap on clarifying questions so the chat can never loop forever even
# if the model keeps wanting more detail -- after this many "ask" turns,
# the system prompt tells it to route NOW with its best guess.
MAX_CLARIFYING_QUESTIONS = int(os.environ.get("SUPPORTROUTER_MAX_CLARIFYING_QUESTIONS", "2"))

FALLBACK_TEAM = TEAM_NAMES[0]


class ChatDecision(BaseModel):
    model_config = {"protected_namespaces": ()}

    action: str  # "ask" | "route"
    message: str
    team: Optional[str] = None
    confidence: Optional[float] = None
    urgency: Optional[str] = None
    reasoning: Optional[str] = None
    secondary_team: Optional[str] = None
    model_version: str = "fallback"


def available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _fallback(reasoning: str) -> ChatDecision:
    return ChatDecision(
        action="route",
        message=(
            "I'm having trouble reaching the classification service right now, "
            "so I've sent this straight to a human for review rather than guess."
        ),
        team=FALLBACK_TEAM,
        confidence=0.0,
        urgency="medium",
        reasoning=reasoning,
        secondary_team=None,
        model_version="fallback",
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    return json.loads(text)


CHAT_INSTRUCTIONS = """\
You are also a CONVERSATIONAL triage assistant embedded in a chat widget, \
not a single-shot classifier. The user may describe their problem briefly \
or vaguely. Your job each turn:

1. If you have enough information to confidently pick a team, respond with \
   action "route".
2. If the request is genuinely ambiguous AND one short clarifying question \
   would meaningfully improve your confidence, respond with action "ask" \
   and put ONLY that one question in "message" (friendly, concise, one \
   sentence, no numbered lists). Do not ask a clarifying question just to \
   be thorough -- only ask if it would actually change which team you'd \
   pick or your urgency assessment.
3. You may ask at most {max_questions} clarifying questions total across \
   the whole conversation. If you have already asked {max_questions} \
   question(s) in this conversation, you MUST respond with action "route" \
   this turn using your best judgment from what you have.

Respond with ONLY a single JSON object, no prose before or after it, no \
markdown fences. Required fields:
{{
  "action": "ask" or "route",
  "message": if action is "ask": your one clarifying question (as a string \
    written directly to the user, e.g. "Is this affecting just you, or the \
    whole team?"). If action is "route": a short, friendly one-sentence \
    confirmation to show the user (e.g. "Got it -- routing this to IT.").
  "team": one of [{team_names}] if action is "route", else null,
  "confidence": a number 0.0-1.0 if action is "route", else null,
  "urgency": one of ["low", "medium", "high"] if action is "route", else null,
  "reasoning": a one-to-two sentence internal explanation if action is \
    "route", else null,
  "secondary_team": one of [{team_names}] or null
}}
"""


def _build_chat_system_prompt(questions_asked_so_far: int) -> str:
    base = build_system_prompt()
    chat_instructions = CHAT_INSTRUCTIONS.format(
        max_questions=MAX_CLARIFYING_QUESTIONS,
        team_names=", ".join(TEAM_NAMES),
    )
    forced_route_note = ""
    if questions_asked_so_far >= MAX_CLARIFYING_QUESTIONS:
        forced_route_note = (
            "\nIMPORTANT: You have already used your clarifying question "
            "budget. You MUST respond with action \"route\" this turn, no "
            "matter how uncertain you are -- lower the confidence score "
            "instead of asking another question.\n"
        )
    return base + "\n" + chat_instructions + forced_route_note


def _call_claude_chat(system_prompt: str, transcript: list[dict], strict: bool = False) -> str:
    messages = [{"role": m["role"], "content": m["content"]} for m in transcript]
    if strict and messages:
        messages[-1] = {
            "role": messages[-1]["role"],
            "content": (
                "Return ONLY a single valid JSON object, with no prose, no "
                "markdown fences, and no explanation before or after it.\n\n"
                + messages[-1]["content"]
            ),
        }
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
            "messages": messages,
        },
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def chat_turn(transcript: list[dict], questions_asked_so_far: int, jira_adapter=None) -> ChatDecision:
    """transcript is the full conversation so far as [{"role": "user"|"assistant",
    "content": str}, ...], ending with the latest user message.
    questions_asked_so_far counts how many "ask" turns the assistant has
    already used in this conversation (caller tracks this).

    If the model is ready to "route" but lands in the uncertain confidence
    band, spends exactly ONE extra call with similar-past-tickets context
    (same token-conscious pattern as classification_service.classify) before
    returning the final decision. jira_adapter is injectable for tests."""
    if not ANTHROPIC_API_KEY:
        return _fallback("[LLM unavailable — ANTHROPIC_API_KEY not set; routed to human review]")

    decision = _chat_turn_once(transcript, questions_asked_so_far)

    if decision.action == "route" and ticket_context.should_enrich(decision.confidence):
        from app.adapters.jira_adapter import get_jira_adapter

        adapter = jira_adapter or get_jira_adapter()
        full_user_text = "\n".join(m["content"] for m in transcript if m["role"] == "user")
        block = ticket_context.fetch_similar_tickets_block(adapter, full_user_text)
        if block:
            # Merge into the LAST message's content rather than appending a
            # new one -- the Anthropic Messages API requires strict
            # user/assistant alternation, and the transcript already ends
            # on a user turn.
            enriched_transcript = [dict(m) for m in transcript]
            enriched_transcript[-1]["content"] = f"{enriched_transcript[-1]['content']}\n\n{block}"
            enriched = _chat_turn_once(enriched_transcript, questions_asked_so_far)
            if enriched.action == "route" and (enriched.confidence or 0.0) > 0:
                enriched.reasoning = f"[enriched with past-ticket history] {enriched.reasoning or ''}".strip()
                return enriched

    return decision


def _chat_turn_once(transcript: list[dict], questions_asked_so_far: int) -> ChatDecision:
    system_prompt = _build_chat_system_prompt(questions_asked_so_far)

    for attempt, strict in enumerate([False, True]):
        try:
            raw_text = _call_claude_chat(system_prompt, transcript, strict=strict)
            parsed = _extract_json(raw_text)
            parsed["model_version"] = ANTHROPIC_MODEL
            decision = ChatDecision(**parsed)

            if decision.action not in ("ask", "route"):
                raise ValueError(f"unexpected action '{decision.action}'")

            # Enforce the clarifying-question budget server-side too, in case
            # the model ignores the instruction.
            if decision.action == "ask" and questions_asked_so_far >= MAX_CLARIFYING_QUESTIONS:
                decision.action = "route"
                if decision.team is None:
                    decision.team = FALLBACK_TEAM
                    decision.confidence = 0.0
                    decision.urgency = decision.urgency or "medium"
                    decision.reasoning = "Clarifying-question budget exhausted without a confident team guess."
                    decision.message = (
                        "I don't have quite enough detail to be confident, so I've "
                        "sent this to a human for review."
                    )

            if decision.action == "route" and decision.team not in TEAM_NAMES:
                decision.confidence = min(decision.confidence or 0.0, 0.3)

            return decision
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError):
            if attempt == 1:
                return _fallback("[LLM returned unparseable output after retry; routed to human review]")
            continue
        except httpx.HTTPStatusError as e:
            return _fallback(f"[Claude API error, HTTP {e.response.status_code}; routed to human review]")
        except httpx.TimeoutException:
            return _fallback("[Claude API timed out; routed to human review]")
        except Exception as e:  # noqa: BLE001
            return _fallback(f"[Claude API call failed: {e}; routed to human review]")

    return _fallback("[Unexpected chat failure; routed to human review]")
