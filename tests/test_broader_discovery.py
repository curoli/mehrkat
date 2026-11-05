from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from mehrkat.config import Settings
from mehrkat.discovery import discover
from mehrkat.listings import SAMPLE
from mehrkat.service import NewsService


def response_for(cited, metadata=(), claim_prefix="Fictional finding"):
    text = ""
    annotations = []
    for number in cited:
        text += f"{claim_prefix} for article {number}. "
        start = len(text)
        text += "[source]"
        annotations.append({
            "type": "url_citation", "url": f"https://example.com/article/{number}?utm_source=test",
            "title": f"Fixture article {number}", "start_index": start, "end_index": len(text),
        })
        text += "\n\n"
    data = {"status": "completed", "output": [
        {"type": "web_search_call", "status": "completed", "action": {"sources": [
            {"url": f"https://example.com/article/{number}"} for number in [*cited, *metadata]
        ]}},
        {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": annotations}]},
    ]}
    return Mock(model_dump=lambda: data)


def test_three_complementary_searches_merge_more_than_four_articles():
    client = Mock()
    client.responses.create.side_effect = [
        response_for(range(4)), response_for(range(3, 7)), response_for(range(6, 10)),
    ]
    now = datetime.now(timezone.utc)
    result = discover(client, "test-model", SAMPLE[0], now, now)
    assert client.responses.create.call_count == 3
    assert len(result.articles) == 10
    assert len({str(a.url) for a in result.articles}) == 10
    assert all(a.evidence_text and a.content_status == "search_evidence" for a in result.articles)
    requests = [call.kwargs for call in client.responses.create.call_args_list]
    assert len({request["input"].split("Search focus: ")[1].split("\n")[0] for request in requests}) == 3
    assert "https://example.com/article/0" in requests[1]["input"]
    assert all(r["tools"][0]["search_context_size"] == "high" for r in requests)
    assert all(r["max_tool_calls"] == 2 and r["max_output_tokens"] == 6000 for r in requests)


def test_cap_prefers_cited_findings_and_stops_before_another_paid_pass():
    client = Mock()
    client.responses.create.return_value = response_for(range(8), metadata=range(8, 30))
    now = datetime.now(timezone.utc)
    result = discover(client, "test-model", SAMPLE[0], now, now, max_articles=6, search_passes=4)
    assert len(result.articles) == 6
    assert all(a.content_status == "search_evidence" for a in result.articles)
    client.responses.create.assert_called_once()


def test_metadata_does_not_stop_search_and_later_citations_upgrade_it():
    client = Mock()
    client.responses.create.side_effect = [
        response_for([], metadata=range(12)),
        response_for([10, 11]),
        response_for([10, 12], claim_prefix="Additional fictional context"),
    ]
    now = datetime.now(timezone.utc)
    result = discover(client, "test-model", SAMPLE[0], now, now, max_articles=5)
    assert client.responses.create.call_count == 3
    assert len(result.articles) == 5
    assert [str(a.url) for a in result.articles[:3]] == [
        "https://example.com/article/10", "https://example.com/article/11", "https://example.com/article/12"]
    assert result.articles[0].title == "Fixture article 10"
    assert "Fictional finding" in result.articles[0].evidence_text
    assert "Additional fictional context" in result.articles[0].evidence_text
    assert result.articles[3].content_status == "metadata_only"


def test_scarce_or_duplicate_results_are_not_invented_to_fill_target():
    client = Mock()
    client.responses.create.return_value = response_for([0, 1])
    now = datetime.now(timezone.utc)
    result = discover(client, "test-model", SAMPLE[0], now, now)
    assert len(result.articles) == 2
    assert client.responses.create.call_count == 3
    assert "Return fewer" in client.responses.create.call_args.kwargs["instructions"]


@pytest.mark.parametrize("max_articles,passes", [(0, 3), (41, 3), (20, 0), (20, 5)])
def test_invalid_limits_fail_before_paid_call(max_articles, passes):
    client = Mock()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        discover(client, "test-model", SAMPLE[0], now, now, max_articles=max_articles, search_passes=passes)
    client.responses.create.assert_not_called()


def test_search_error_is_not_hidden_as_complete_discovery():
    client = Mock()
    client.responses.create.side_effect = [response_for([0]), RuntimeError("fixture failure")]
    now = datetime.now(timezone.utc)
    with pytest.raises(RuntimeError, match="fixture failure"):
        discover(client, "test-model", SAMPLE[0], now, now)
    assert client.responses.create.call_count == 2


def test_discovery_budget_settings_invalidate_discovery_cache(settings, client):
    service = NewsService(settings, client)
    service.run(SAMPLE[0], 48)
    service.run(SAMPLE[0], 48)
    assert client.responses.create.call_count == 1
    settings.discovery_search_passes = 2
    changed = service.run(SAMPLE[0], 48)
    assert not changed.discovery_cached
    assert client.responses.create.call_count == 3
    settings.max_articles = 10
    assert not service.run(SAMPLE[0], 48).discovery_cached
    assert client.responses.create.call_count == 5


def test_default_discovery_budgets():
    settings = Settings()
    assert settings.max_articles == 20
    assert settings.discovery_search_passes == 3


@pytest.mark.parametrize("articles,passes,expected", [("80", "9", (40, 4)), ("0", "0", (1, 1)), ("12", "2", (12, 2))])
def test_environment_budgets_are_bounded(monkeypatch, articles, passes, expected):
    # Avoid loading the owner's .env: this test provides explicit configuration.
    monkeypatch.setattr("mehrkat.config.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("NEWS_MAX_ARTICLES", articles)
    monkeypatch.setenv("DISCOVERY_SEARCH_PASSES", passes)
    settings = Settings.from_env()
    assert (settings.max_articles, settings.discovery_search_passes) == expected
