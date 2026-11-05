import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError, APIStatusError, APITimeoutError

from mehrkat.app import create_app


def test_search_select_summary_and_citations(settings, client):
    app = TestClient(create_app(settings, client))
    home = app.get("/")
    assert home.status_code == 200 and 'id="search"' in home.text
    rows = app.get("/api/listings?q=SAP").json()
    assert len(rows) == 2
    assert app.get("/listing", params={"key": rows[0]["listing_key"]}).status_code == 200
    for page in ["/settings", "/monitoring", "/debug"]:
        assert page in home.text and app.get(page).status_code == 200
    client.responses.create.assert_not_called()
    client.responses.parse.assert_not_called()
    response = app.post("/api/summary?key=NASDAQ:AAPL")
    assert response.status_code == 200
    html = app.get("/result").text
    assert 'href="https://example.com/news"' in html
    assert "Publication date unknown/unverified" in html
    assert "Fictional test summary" in html
    assert app.get("/debug").status_code == 200
    assert app.get("/api/summary?key=NASDAQ:AAPL").status_code == 405
    assert app.post("/api/summary?key=NASDAQ:AAPL&hours=0").status_code == 422


def test_missing_key_and_unknown_listing(settings):
    app = TestClient(create_app(settings))
    assert app.get("/").status_code == 200
    assert app.post("/api/summary?key=missing").status_code == 404
    response = app.post("/api/summary?key=NASDAQ:AAPL")
    assert response.status_code == 422 and "OPENAI_API_KEY" in response.text


@pytest.mark.parametrize("kind,code,expected", [("timeout", 0, 504), ("connection", 0, 502), ("status", 401, 502), ("status", 429, 502), ("status", 404, 502)])
def test_sanitized_errors(settings, client, kind, code, expected):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    if kind == "timeout":
        error = APITimeoutError(request=request)
    elif kind == "connection":
        error = APIConnectionError(request=request)
    else:
        error = APIStatusError("private-provider-message", response=httpx.Response(code, request=request), body=None)
    client.responses.create.side_effect = error
    app = TestClient(create_app(settings, client))
    response = app.post("/api/summary?key=NASDAQ:AAPL")
    assert response.status_code == expected
    assert "private-provider-message" not in response.text


def test_concurrent_request_is_bounded(settings, client):
    application = create_app(settings, client)
    application.state.service.lock.acquire()
    try:
        assert TestClient(application).post("/api/summary?key=NASDAQ:AAPL").status_code == 409
        client.responses.create.assert_not_called()
    finally:
        application.state.service.lock.release()


def test_article_coverage_shown_without_returning_bodies(settings, client, monkeypatch):
    from datetime import datetime, timezone
    from mehrkat.articles import ArticleRetriever, ArticleText
    article_body = "Publisher article body for internal analysis only. " * 10
    monkeypatch.setattr(ArticleRetriever, "get", lambda self, url: ArticleText(
        text=article_body, status="article_text", note="Extracted article text; completeness unverified.",
        retrieved_at=datetime.now(timezone.utc), final_url=url,
    ))
    application = create_app(settings, client)
    app = TestClient(application)
    response = app.post("/api/summary?key=NASDAQ:AAPL")
    assert response.status_code == 200
    source = response.json()["discovery"]["articles"][0]
    assert source["content_status"] == "article_text"
    assert "evidence_text" not in source and "search_evidence_text" not in source
    assert article_body not in response.text
    page = app.get("/result").text
    assert "Extracted article text (completeness unverified)" in page
    assert article_body not in page
    assert article_body not in app.get("/debug").text
    assert article_body in client.responses.parse.call_args.kwargs["input"]


def test_listing_filters_and_navigation(settings, client):
    from html.parser import HTMLParser
    from urllib.parse import parse_qs, urlsplit

    class PageParser(HTMLParser):
        def __init__(self, text):
            super().__init__()
            self.links = []
            self.checked = []
            self.feed(text)

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == "a":
                self.links.append(attrs["href"])
            if tag == "input" and "checked" in attrs:
                self.checked.append((attrs["name"], attrs["value"]))

    app = TestClient(create_app(settings, client))
    params = [("q", "SAP"), ("exchange", "NYSE"), ("exchange", "XETRA"), ("country", "Germany"), ("sector", "Technology")]
    response = app.get("/api/listings", params=params)
    assert response.status_code == 200
    assert {r["exchange"] for r in response.json()} == {"NYSE", "XETRA"}
    assert app.get("/api/listings", params={"country": "Germany"}).json()
    assert app.get("/api/listings", params={"q": "SAP", "country": "United States"}).json() == []
    home = app.get("/", params=params)
    assert set(PageParser(home.text).checked) == set(params[1:])
    listing = app.get("/listing", params=[("key", "NYSE:SAP"), *params])
    return_link = next(link for link in PageParser(listing.text).links if link.startswith("/?"))
    assert parse_qs(urlsplit(return_link).query) == {
        "q": ["SAP"], "exchange": ["NYSE", "XETRA"], "country": ["Germany"], "sector": ["Technology"],
    }
    client.responses.create.assert_not_called()
    client.responses.parse.assert_not_called()
    assert app.post("/api/summary", params={"key": "NASDAQ:AAPL"}).status_code == 200
    result = app.get("/result", params=params)
    assert return_link in PageParser(result.text).links


@pytest.mark.parametrize("exchanges", [["nyse"], [" nyse ", "xEtRa"]])
def test_normalized_filters_survive_return_navigation(settings, client, exchanges):
    from html.parser import HTMLParser

    class SearchPage(HTMLParser):
        def __init__(self, text):
            super().__init__()
            self.checked = []
            self.return_link = None
            self.feed(text)

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == "input" and "checked" in attrs:
                self.checked.append((attrs["name"], attrs["value"]))
            if tag == "a" and attrs.get("href", "").startswith("/?"):
                self.return_link = attrs["href"]

    app = TestClient(create_app(settings, client))
    params = [("q", "SAP"), *[("exchange", value) for value in exchanges],
              ("country", " gErMaNy "), ("sector", " TECHNOLOGY ")]
    expected = {value.strip().upper() for value in exchanges}
    original = app.get("/api/listings", params=params).json()
    assert {row["exchange"] for row in original} == expected

    def check_restored_page(response):
        assert response.status_code == 200
        page = SearchPage(response.text)
        assert set(page.checked) == {
            *[("exchange", value) for value in expected],
            ("country", "Germany"), ("sector", "Technology"),
        }
        # JavaScript submits the canonical values from checked checkboxes.
        restored = app.get("/api/listings", params=[("q", "SAP"), *page.checked]).json()
        assert restored == original

    check_restored_page(app.get("/", params=params))
    listing = app.get("/listing", params=[("key", "NYSE:SAP"), *params])
    check_restored_page(app.get(SearchPage(listing.text).return_link))
    client.responses.create.assert_not_called()
    client.responses.parse.assert_not_called()

    assert app.post("/api/summary", params={"key": "NASDAQ:AAPL"}).status_code == 200
    result = app.get("/result", params=params)
    check_restored_page(app.get(SearchPage(result.text).return_link))


def test_result_coverage_totals_and_no_duplicate_model_caveats(settings, client, briefing):
    duplicate = "Coverage warning shown once."
    application = create_app(settings, client)
    app = TestClient(application)
    response = app.post("/api/summary?key=NASDAQ:AAPL")
    assert response.status_code == 200
    assert response.json()["coverage"] == {
        "evaluated_sources": 2, "used_articles": 1, "full_text_articles": 0,
        "excerpt_articles": 0, "search_summary_articles": 1,
    }
    result = application.state.service.last_result
    result.discovery.limitations = [duplicate, " coverage warning shown once "]
    result.briefing.limitations = [duplicate, "Model-specific caveat"]
    html = app.get("/result").text
    assert html.count(duplicate) == 1
    assert "Articles used: 1" in html
    assert "Full text extracted: 0" in html
    assert "Search summaries: 1" in html
    assert "completeness is unverified" in html
    assert "Model-specific caveat" not in html
    assert "Model-specific caveat" in app.get("/debug").text
    # Cached responses still compute the same statistics.
    repeated = app.post("/api/summary?key=NASDAQ:AAPL")
    assert repeated.json()["summary_cached"]
    assert repeated.json()["coverage"] == response.json()["coverage"]


@pytest.mark.parametrize("params,expected", [
    ([], {"exchange": 0, "country": 0, "sector": 0}),
    ([("q", "SAP"), ("exchange", "nyse"), ("exchange", " NYSE "),
      ("exchange", "XETRA"), ("country", " germany "), ("sector", "Technology")],
     {"exchange": 2, "country": 1, "sector": 1}),
])
def test_filter_counts_and_reset_controls_are_rendered(settings, client, params, expected):
    from html.parser import HTMLParser

    class Controls(HTMLParser):
        def __init__(self, text):
            super().__init__()
            self.counts = {}
            self.buttons = {}
            self.current_count = None
            self.feed(text)

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == "span" and attrs.get("id", "").startswith("count-"):
                self.current_count = attrs["id"]
            if tag == "button" and attrs.get("id", "").startswith("reset-"):
                self.buttons[attrs["id"]] = attrs

        def handle_data(self, text):
            if self.current_count:
                self.counts[self.current_count] = text

        def handle_endtag(self, tag):
            if tag == "span":
                self.current_count = None

    app = TestClient(create_app(settings, client))
    response = app.get("/", params=params)
    assert response.status_code == 200
    controls = Controls(response.text)
    for name, count in expected.items():
        assert controls.counts["count-" + name] == f"{count} selected"
        button = controls.buttons["reset-" + name]
        assert button["type"] == "button"
        assert ("disabled" in button) is (count == 0)
    client.responses.create.assert_not_called()
    client.responses.parse.assert_not_called()
