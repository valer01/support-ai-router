"""
Ticket-history enrichment — a token-conscious confidence booster.

Only triggered when a first-pass classification lands in an uncertain
confidence band (see SUPPORTROUTER_ENRICHMENT_CONFIDENCE_THRESHOLD, default
0.85). Rather than attaching full ticket bodies or querying on every
request, we search Jira (or the mock ticket store in dev) for a handful of
textually similar PAST tickets, compress each to a one-line
"KEY: summary -> resolved by TEAM" fact (no descriptions/comments), and
spend exactly ONE extra bounded LLM call with that context. Clear-cut
requests (the large majority, per the golden-set test) never pay this cost
at all -- this keeps the token/dollar overhead close to zero in aggregate
while still giving the model real historical precedent on the genuinely
ambiguous cases where it helps most.
"""
from __future__ import annotations
import os

from app.adapters.jira_adapter import JiraAdapterProtocol
from app.routing_matrix import TEAMS

ENRICHMENT_CONFIDENCE_THRESHOLD = float(
    os.environ.get("SUPPORTROUTER_ENRICHMENT_CONFIDENCE_THRESHOLD", "0.85")
)
SIMILAR_TICKETS_LIMIT = int(os.environ.get("SUPPORTROUTER_SIMILAR_TICKETS_LIMIT", "5"))

_PROJECT_KEY_TO_TEAM = {t["jira_project_key"]: t["name"] for t in TEAMS}


def should_enrich(confidence: float | None) -> bool:
    """0.0 means the first pass already hit a hard failure (no API key,
    unparseable response, etc.) -- no point spending another call in that
    case. Above the threshold, the model was already confident enough."""
    if confidence is None:
        return False
    return 0.0 < confidence < ENRICHMENT_CONFIDENCE_THRESHOLD


def fetch_similar_tickets_block(jira_adapter: JiraAdapterProtocol, query_text: str) -> str | None:
    """Returns a compact, prompt-ready text block of similar past tickets,
    or None if none were found or the lookup failed. Never raises -- a
    broken/unreachable Jira should degrade to "no extra context", not
    break classification."""
    try:
        tickets = jira_adapter.search_similar_tickets(query_text, limit=SIMILAR_TICKETS_LIMIT)
    except Exception:
        return None
    if not tickets:
        return None
    lines = []
    for t in tickets:
        team = _PROJECT_KEY_TO_TEAM.get(t.get("project_key", ""), t.get("project_key", "unknown"))
        summary = (t.get("summary") or "").replace("\n", " ")[:150]
        lines.append(f'- {t.get("key")}: "{summary}" -> resolved by {team}')
    return (
        "Similar past tickets (extra context for confidence, not a "
        "guarantee -- use your own judgment if they seem like a mismatch "
        "for this request):\n" + "\n".join(lines)
    )
