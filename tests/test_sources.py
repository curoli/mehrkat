import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from mehrkat.app import create_app
from mehrkat.articles import ArticleRetriever, ArticleText


class SourcePage(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.texts = []
        self.in_pre = False
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        if tag == "a":
            self.links.append(dict(attributes).get("href", ""))
        if tag == "pre":
            self.in_pre = True
            self.texts.append("")

    def handle_data(self, data):
        if self.in_pre:
            self.texts[-1] += data

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_pre = False


@pytest.mark.parametrize("status", ["article_text", "excerpt", "search_evidence"])
def test_source_list_and_viewer_show_exact_supplied_text(settings, client, briefing, monkeypatch, status):
    text = "Fictional publisher body <script>alert('test')</script> & more\nSecond paragraph."
    payload = ArticleText(
        text="" if status == "search_evidence" else text,
        status="unavailable" if status == "search_evidence" else status,
        note="Test extraction", retrieved_at=datetime.now(timezone.utc),
    )
    retrieval = Mock(return_value=payload)
    monkeypatch.setattr(ArticleRetriever, "get", retrieval)
    # Reusing one source in multiple developments must produce one list entry.
    briefing.developments.append(briefing.developments[0].model_copy())
    app = TestClient(create_app(settings, client))
    response = app.post("/api/summary?key=NASDAQ:AAPL")
    assert response.status_code == 200
    data = response.json()
    source_id = data["discovery"]["articles"][0]["id"]
    query = [("briefing", data["result_id"]), ("q", "SAP & alias"),
             ("exchange", "NYSE"), ("exchange", "XETRA"), ("country", "Germany")]
    result = app.get("/result", params=query)
    page = SourcePage(result.text)
    viewers = [link for link in page.links if link.startswith("/sources/")]
    assert len(viewers) == 1
    assert "Sources used" in result.text and "https://example.com/news" in result.text
    assert "https://example.com/news" in page.links
    assert parse_qs(urlsplit(viewers[0]).query)["exchange"] == ["NYSE", "XETRA"]
    assert source_id in viewers[0]
    calls_before = (client.responses.create.call_count, client.responses.parse.call_count, retrieval.call_count)
    viewer = app.get(viewers[0])
    assert viewer.status_code == 200
    assert viewer.headers["cache-control"] == "no-store"
    supplied = json.loads(client.responses.parse.call_args.kwargs["input"].split("\nEvidence: ", 1)[1])
    article = next(a for a in supplied["articles"] if a["id"] == source_id)
    viewed = SourcePage(viewer.text)
    assert viewed.texts[0] == article["evidence_text"]
    if article["search_evidence_text"]:
        assert viewed.texts[1] == article["search_evidence_text"]
    if status == "search_evidence":
        assert "not publisher article text" in viewer.text
    else:
        assert "<script>alert('test')</script>" not in viewer.text
        assert text in viewed.texts
    assert calls_before == (client.responses.create.call_count, client.responses.parse.call_count, retrieval.call_count)
    back = next(link for link in viewed.links if link.startswith("/result?"))
    assert parse_qs(urlsplit(back).query)["briefing"] == [data["result_id"]]
    assert parse_qs(urlsplit(back).query)["exchange"] == ["NYSE", "XETRA"]
    assert app.get(back).status_code == 200


def test_source_snapshot_survives_new_generation_and_restart(settings, client, monkeypatch):
    state = {"text": "Original cached source text"}
    retrieval = Mock(side_effect=lambda url: ArticleText(
        text=state["text"], status="article_text", note="Test",
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ))
    monkeypatch.setattr(ArticleRetriever, "get", retrieval)
    application = create_app(settings, client)
    app = TestClient(application)
    first = app.post("/api/summary?key=NASDAQ:AAPL").json()
    source_id = first["discovery"]["articles"][0]["id"]
    original_url = f"/sources/{first['result_id']}/{source_id}"
    repeated = app.post("/api/summary?key=NASDAQ:AAPL").json()
    assert repeated["summary_cached"] and repeated["result_id"] == first["result_id"]
    state["text"] = "Newer source text that must not replace the original"
    second = app.post("/api/summary?key=NASDAQ:AAPL").json()
    assert second["result_id"] != first["result_id"]
    old = app.get(original_url)
    assert SourcePage(old.text).texts[0] == "Original cached source text"
    second_url = f"/sources/{second['result_id']}/{source_id}"
    assert SourcePage(app.get(second_url).text).texts[0] == state["text"]

    # New process state can read exact snapshots without credentials or network.
    settings.api_key = ""
    new_client = Mock()
    restarted = TestClient(create_app(settings, new_client))
    prior_retrievals = retrieval.call_count
    assert SourcePage(restarted.get(original_url).text).texts[0] == "Original cached source text"
    assert restarted.get("/result", params={"briefing": first["result_id"]}).status_code == 200
    new_client.responses.create.assert_not_called()
    new_client.responses.parse.assert_not_called()
    assert retrieval.call_count == prior_retrievals


def test_viewer_uses_budget_limited_evidence_not_full_url_cache(settings, client, monkeypatch):
    monkeypatch.setattr("mehrkat.articles.MAX_BRIEFING_TEXT", 250)
    monkeypatch.setattr(ArticleRetriever, "get", lambda self, url: ArticleText(
        text="A" * 500, status="article_text", note="Test",
        retrieved_at=datetime.now(timezone.utc),
    ))
    app = TestClient(create_app(settings, client))
    result = app.post("/api/summary?key=NASDAQ:AAPL").json()
    source_id = result["discovery"]["articles"][0]["id"]
    page = app.get(f"/sources/{result['result_id']}/{source_id}")
    assert SourcePage(page.text).texts[0] == "A" * 250
    assert "truncated before summarization" in page.text


def test_expired_unknown_and_uncited_sources_never_fetch(settings, client, monkeypatch):
    app_instance = create_app(settings, client)
    app = TestClient(app_instance)
    data = app.post("/api/summary?key=NASDAQ:AAPL").json()
    result_id = data["result_id"]
    cited, uncited = data["discovery"]["articles"]
    retrieval = Mock(side_effect=AssertionError("Viewer must never retrieve text"))
    monkeypatch.setattr(ArticleRetriever, "get", retrieval)
    for path in [f"/sources/{result_id}/{uncited['id']}", f"/sources/{result_id}/unknown", "/sources/unknown/source"]:
        assert app.get(path).status_code == 404
    with app_instance.state.service.cache.connect() as db:
        db.execute("UPDATE cache SET expires=0 WHERE key LIKE 'result:%'")
    expired = app.get(f"/sources/{result_id}/{cited['id']}")
    assert expired.status_code == 404 and "expired" in expired.text
    assert app.get("/result", params={"briefing": result_id}).status_code == 404
    retrieval.assert_not_called()
    assert client.responses.create.call_count == client.responses.parse.call_count == 1


def test_no_cited_sources_gives_empty_list_and_no_text_access(settings, client, briefing):
    briefing.developments = []
    briefing.insufficient_news = True
    app = TestClient(create_app(settings, client))
    result = app.post("/api/summary?key=NASDAQ:AAPL").json()
    page = app.get("/result", params={"briefing": result["result_id"]})
    assert "No sources were cited in this briefing." in page.text
    assert "0 sources cited · 2 evaluated" in page.text
    assert not any(link.startswith("/sources/") for link in SourcePage(page.text).links)
    article = result["discovery"]["articles"][0]
    assert app.get(f"/sources/{result['result_id']}/{article['id']}").status_code == 404
