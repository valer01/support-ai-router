"""Unit tests for MockJiraAdapter.search_similar_tickets keyword scoring."""
from app.adapters.jira_adapter import MockJiraAdapter


def test_search_similar_tickets_ranks_by_keyword_overlap():
    adapter = MockJiraAdapter()
    adapter.create_ticket("ITSUP", "Can't connect to VPN from home", "desc")
    adapter.create_ticket("ITSUP", "VPN client crashes on startup", "desc")
    adapter.create_ticket("DEVOPS", "Deploy pipeline failing on main", "desc")

    results = adapter.search_similar_tickets("VPN connection issue", limit=5)

    assert len(results) == 2
    assert all(r["project_key"] == "ITSUP" for r in results)
    assert all("key" in r and "summary" in r for r in results)


def test_search_similar_tickets_returns_empty_for_no_matches():
    adapter = MockJiraAdapter()
    adapter.create_ticket("ITSUP", "Laptop screen flickering", "desc")

    results = adapter.search_similar_tickets("pricing model NaN calculation", limit=5)

    assert results == []


def test_search_similar_tickets_respects_limit():
    adapter = MockJiraAdapter()
    for i in range(10):
        adapter.create_ticket("ITSUP", f"VPN connection problem number {i}", "desc")

    results = adapter.search_similar_tickets("VPN connection", limit=3)

    assert len(results) == 3
