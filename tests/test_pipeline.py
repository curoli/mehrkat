from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from mehrkat import discovery, summarization
from mehrkat.listings import SAMPLE


def test_native_sources_and_unknown_dates(evidence):
    assert len(evidence.articles) == 2
    article = evidence.articles[0]
    assert str(article.url) == "https://example.com/news"
    assert article.evidence_text.startswith("Fictional test event")
    assert article.published_at is None
    assert article.published_at_verified is False
    assert evidence.articles[1].content_status == "metadata_only"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "https://user:password@example.com", "http://["])
def test_bad_urls(url):
    assert discovery.canonical_url(url) is None


def test_search_call_required(response_data):
    response_data["output"] = response_data["output"][1:]
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="did not perform"):
        discovery.extract_discovery(Mock(model_dump=lambda: response_data), SAMPLE[0], now, now)


def test_request_contract(client, evidence):
    discovery.discover(client, "test-model", SAMPLE[0], evidence.window_start, evidence.window_end)
    request = client.responses.create.call_args.kwargs
    assert "Apple Inc." in request["input"]
    assert "NASDAQ" in request["input"]
    assert request["tools"][0]["type"] == "web_search"
    assert request["include"] == ["web_search_call.action.sources"]
    summarization.summarize(client, "test-model", SAMPLE[0], evidence)
    request = client.responses.parse.call_args.kwargs
    assert "tools" not in request
    assert "Merge reports" in request["instructions"]


def test_unknown_citation_rejected(briefing, evidence):
    briefing.developments[0].source_ids = ["invented"]
    with pytest.raises(ValueError, match="unknown"):
        summarization.validate_sources(briefing, evidence)


def test_uncertain_and_metadata_cannot_support_claims(briefing, evidence):
    briefing.developments[0].source_ids = [evidence.articles[1].id]
    with pytest.raises(ValueError, match="uncertain"):
        summarization.validate_sources(briefing, evidence)


def test_missing_relevance_rejected(briefing, evidence):
    briefing.relevance = []
    with pytest.raises(ValueError, match="each source"):
        summarization.validate_sources(briefing, evidence)


def test_refusal(client, evidence):
    client.responses.parse.return_value.output_parsed = None
    with pytest.raises(ValueError, match="refused"):
        summarization.summarize(client, "test-model", SAMPLE[0], evidence)


def test_empty_evidence_insufficient(client, evidence, briefing):
    evidence.articles = []
    briefing.developments = []
    briefing.relevance = []
    briefing.insufficient_news = True
    result = summarization.summarize(client, "test-model", SAMPLE[0], evidence)
    assert result.insufficient_news and not result.developments
