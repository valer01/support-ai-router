"""Unit tests for ticket_context.should_enrich / fetch_similar_tickets_block."""
from unittest.mock import MagicMock

from app.services import ticket_context


def test_should_enrich_true_for_uncertain_confidence():
    assert ticket_context.should_enrich(0.6) is True


def test_should_enrich_false_for_high_confidence():
    assert ticket_context.should_enrich(0.95) is False


def test_should_enrich_false_for_zero_confidence_hard_failure():
    # 0.0 means the first pass already hard-failed (no API key, unparseable,
    # etc.) -- no point spending another call.
    assert ticket_context.should_enrich(0.0) is False


def test_should_enrich_false_for_none():
    assert ticket_context.should_enrich(None) is False


def test_fetch_similar_tickets_block_formats_compact_summary():
    adapter = MagicMock()
    adapter.search_similar_tickets.return_value = [
        {"key": "ITSUP-842", "summary": "Can't reach VPN from home", "project_key": "ITSUP"},
    ]

    block = ticket_context.fetch_similar_tickets_block(adapter, "vpn issue")

    assert block is not None
    assert "ITSUP-842" in block
    assert "IT" in block  # resolved-by-team label derived from project_key


def test_fetch_similar_tickets_block_returns_none_on_empty():
    adapter = MagicMock()
    adapter.search_similar_tickets.return_value = []

    assert ticket_context.fetch_similar_tickets_block(adapter, "vpn issue") is None


def test_fetch_similar_tickets_block_returns_none_on_adapter_error():
    adapter = MagicMock()
    adapter.search_similar_tickets.side_effect = RuntimeError("jira down")

    assert ticket_context.fetch_similar_tickets_block(adapter, "vpn issue") is None
