from datetime import datetime, timezone

import pytest

from mehrkat.listings import SAMPLE
from mehrkat.models import SummaryResult


def make_result(evidence, briefing):
    return SummaryResult(
        listing=SAMPLE[0], discovery=evidence, briefing=briefing,
        generated_at=datetime.now(timezone.utc), discovery_cached=False, summary_cached=False,
    )


def test_coverage_counts_unique_cited_sources_by_actual_input(evidence, briefing):
    first = evidence.articles[0]
    first.content_status = "article_text"
    excerpt = first.model_copy(update={"id": "excerpt", "content_status": "excerpt"})
    search = first.model_copy(update={"id": "search", "content_status": "search_evidence"})
    uncited = first.model_copy(update={"id": "uncited", "content_status": "article_text"})
    evidence.articles.extend([excerpt, search, uncited])
    briefing.developments[0].source_ids = [first.id, "excerpt", "search", first.id]
    briefing.developments.append(briefing.developments[0].model_copy())
    result = make_result(evidence, briefing)
    assert result.coverage.model_dump() == {
        "evaluated_sources": 5, "used_articles": 3, "full_text_articles": 1,
        "excerpt_articles": 1, "search_summary_articles": 1,
    }
    assert result.model_dump(mode="json")["coverage"]["used_articles"] == 3


@pytest.mark.parametrize("status", ["metadata_only", "search_evidence", "article_text", "excerpt"])
def test_insufficient_news_counts_no_articles_as_used(evidence, briefing, status):
    evidence.articles[0].content_status = status
    briefing.insufficient_news = True
    briefing.developments = []
    result = make_result(evidence, briefing)
    assert result.coverage.used_articles == 0
    assert result.coverage.full_text_articles == 0
    assert result.coverage.excerpt_articles == 0
    assert result.coverage.search_summary_articles == 0


def test_coverage_notes_have_one_authoritative_source(evidence, briefing):
    evidence.limitations = ["Publication dates unverified.", " publication   DATES unverified ", "", "Other limitation"]
    briefing.limitations = ["Publication dates unverified.", "Different wording of the same generic caveat"]
    result = make_result(evidence, briefing)
    assert result.coverage_notes == ["Publication dates unverified.", "Other limitation"]
