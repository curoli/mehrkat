from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mehrkat.config import Settings
from mehrkat.discovery import extract_discovery
from mehrkat.listings import SAMPLE
from mehrkat.models import StockBriefing


@pytest.fixture
def settings(tmp_path):
    # Most workflow fixtures isolate a single search pass; broader discovery
    # has dedicated multi-response and cache-configuration tests.
    return Settings(cache_path=tmp_path / "cache.sqlite", listings_path=tmp_path / "absent.csv",
                    discovery_search_passes=1)


@pytest.fixture
def response_data():
    claim = "Fictional test event: Apple announced a product. "
    return {
        "status": "completed",
        "output": [
            {"type": "web_search_call", "status": "completed", "action": {"sources": [
                {"url": "https://example.com/news?utm_source=test"},
                {"url": "https://example.com/news"},
                {"url": "https://example.com/metadata"},
                {"url": "javascript:alert(1)"},
            ]}},
            {"type": "message", "content": [{"type": "output_text", "text": claim + "[1]",
                "annotations": [{"type": "url_citation", "url": "https://example.com/news", "title": "Test source",
                                 "start_index": len(claim), "end_index": len(claim) + 3}]}]},
        ],
    }


@pytest.fixture
def evidence(response_data):
    now = datetime.now(timezone.utc)
    return extract_discovery(Mock(model_dump=lambda: response_data), SAMPLE[0], now, now)


@pytest.fixture
def briefing(evidence):
    return StockBriefing(
        overview="Fictional test summary.", insufficient_news=False, limitations=["Fixture only"],
        relevance=[{"article_id": a.id, "category": "direct" if a.evidence_text else "uncertain", "reason": "Test"} for a in evidence.articles],
        developments=[{"title": "One event", "factual_summary": "Fictional event.",
                       "possible_implications": "Could affect demand.", "source_ids": [evidence.articles[0].id]}],
    )


@pytest.fixture
def client(response_data, briefing):
    client = Mock()
    client.responses.create.return_value = Mock(model_dump=lambda: response_data)
    template_response = SimpleNamespace(status="completed", output_parsed=briefing)
    client.responses.parse.return_value = template_response

    def parse(**kwargs):
        if template_response.output_parsed is None:
            return template_response
        payload = template_response.output_parsed.model_dump()
        payload["relevance"] = {
            decision["article_id"]: {key: decision[key] for key in ("category", "reason")}
            for decision in payload["relevance"]
        }
        return SimpleNamespace(status=template_response.status,
                               output_parsed=kwargs["text_format"].model_validate(payload))

    client.responses.parse.side_effect = parse
    return client


@pytest.fixture(autouse=True)
def no_article_network(monkeypatch):
    # Existing workflow tests keep their search-only fixtures. Article retrieval
    # tests inject their own HTTP/extractor fakes explicitly.
    from mehrkat.articles import ArticleRetriever, ArticleText
    monkeypatch.setattr(ArticleRetriever, "get", lambda self, url: ArticleText(
        note="Fixture retrieval unavailable", retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
    ))


@pytest.fixture(autouse=True)
def block_outbound_connections(monkeypatch):
    import socket

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def connect(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("Tests must mock network access; real connections are disabled.")
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("Tests must mock network access; real connections are disabled.")
        return original_connect_ex(sock, address)

    # Leave local Unix socket pairs available for TestClient's event loop.
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
