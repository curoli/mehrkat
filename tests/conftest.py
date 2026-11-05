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
    return Settings(cache_path=tmp_path / "cache.sqlite", listings_path=tmp_path / "absent.csv")


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
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=briefing)
    return client
