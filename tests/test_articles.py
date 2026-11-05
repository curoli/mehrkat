from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from mehrkat import articles
from mehrkat.articles import ArticleRetriever, ArticleText, RetrievalError
from mehrkat.cache import Cache, content_key
from mehrkat.listings import SAMPLE
from mehrkat.service import NewsService

# Undo the suite's no-network ArticleRetriever.get stub for cache-specific tests.
REAL_GET = ArticleRetriever.get


@pytest.fixture
def article_cache(settings):
    return Cache(settings.cache_path)


@pytest.fixture
def restore_get(monkeypatch):
    monkeypatch.setattr(ArticleRetriever, "get", REAL_GET)


@pytest.mark.parametrize("url,addresses", [
    ("https://127.0.0.1/page", ["127.0.0.1"]),
    ("https://example.com", ["93.184.216.34", "10.0.0.1"]),
    ("https://example.com", ["169.254.169.254"]),
    ("https://example.com", ["::1"]),
    ("https://example.com", ["::ffff:127.0.0.1"]),
    ("file:///etc/passwd", []),
    ("https://user:secret@example.com", []),
    ("http://example.com:8080", []),
])
def test_private_and_unsupported_destinations_blocked(monkeypatch, url, addresses):
    monkeypatch.setattr(articles.socket, "getaddrinfo", lambda *a, **k: [
        (0, 0, 0, "", (ip, 443)) for ip in addresses])
    with pytest.raises(RetrievalError):
        articles.public_address(url)


def test_transport_pins_validated_ip_and_preserves_tls_hostname(monkeypatch):
    monkeypatch.setattr(articles, "public_address",
                        lambda url: (articles.urlsplit(url), "93.184.216.34"))
    sock = Mock()
    create = Mock(return_value=sock)
    monkeypatch.setattr(articles.socket, "create_connection", create)
    tls = Mock()
    tls.wrap_socket.return_value = sock
    monkeypatch.setattr(articles.ssl, "create_default_context", lambda: tls)
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = 200
    response.getheaders.return_value = [("Content-Type", "text/html")]
    response.read1.side_effect = [b"<article>text</article>", b""]
    constructor = Mock(return_value=connection)
    monkeypatch.setattr(articles.http.client, "HTTPConnection", constructor)
    status, headers, body = articles.request_page("https://example.com/page?q=1", articles.monotonic() + 8)
    assert status == 200 and b"article" in body
    assert create.call_args.args[0] == ("93.184.216.34", 443)
    tls.wrap_socket.assert_called_once_with(sock, server_hostname="example.com")
    assert constructor.call_args.args == ("example.com", 443)
    assert connection.request.call_args.args == ("GET", "/page?q=1")
    assert connection.request.call_args.kwargs["headers"]["User-Agent"] == "Mehrkat/0.1"
    connection.close.assert_called_once()


@pytest.mark.parametrize("rules,allowed", [
    (b"User-agent: *\nDisallow: /news", False),
    (b"User-agent: *\nAllow: /", True),
    (b"User-agent: Mehrkat\nDisallow: /", False),
    (b"User-agent: *\nCrawl-delay: 10", False),
])
def test_robots_rules(monkeypatch, rules, allowed):
    monkeypatch.setattr(articles, "request_page", lambda *a: (200, {}, rules))
    assert articles.robots_allowed("https://example.com/news", 1) is allowed


@pytest.mark.parametrize("status,allowed", [(404, True), (403, False), (500, False), (302, False)])
def test_robots_unavailable_fails_closed(monkeypatch, status, allowed):
    monkeypatch.setattr(articles, "request_page", lambda *a: (status, {}, b""))
    assert articles.robots_allowed("https://example.com/news", 1) is allowed


def test_extract_real_html_without_navigation(monkeypatch):
    paragraphs = [
        "A fictional company announced a new manufacturing facility in this test article. "
        "The investment covers equipment and staff training, according to its public announcement.",
        "The facility is expected to begin operating next year. The timetable remains subject "
        "to planning approvals and the completion of construction work.",
        "Management described the project as part of its longer term capacity expansion. "
        "This fixture contains invented information solely for deterministic testing.",
    ]
    body = ("<html><body><nav>Home Contact</nav><article><h1>Test news</h1>" +
            "".join(f"<p>{p}</p>" for p in paragraphs) + "</article></body></html>").encode()
    monkeypatch.setattr(articles, "robots_allowed", lambda *a: True)
    monkeypatch.setattr(articles, "request_page", lambda *a: (200, {"content-type": "text/html"}, body))
    result = articles.retrieve("https://example.com/news")
    assert result.status == "article_text"
    assert all(p in result.text for p in paragraphs)
    assert "Home Contact" not in result.text
    assert "completeness unverified" in result.note


@pytest.mark.parametrize("kind", ["http", "pdf", "short", "restricted", "paywall", "timeout", "parser", "robots", "long"])
def test_retrieval_outcomes(monkeypatch, kind):
    monkeypatch.setattr(articles, "robots_allowed", lambda *a: kind != "robots")
    body = b'<html><script>{"isAccessibleForFree":false}</script></html>' if kind == "restricted" else b"<html></html>"
    def request(*args):
        if kind == "timeout":
            raise TimeoutError()
        return (403 if kind == "http" else 200,
                {"content-type": "application/pdf" if kind == "pdf" else "text/html"}, body)
    monkeypatch.setattr(articles, "request_page", request)
    def extract(*a, **kw):
        if kind == "parser":
            raise RuntimeError("private parser payload")
        return "Subscribe to read " * 30 if kind == "paywall" else "short" if kind == "short" else "x" * 30001
    monkeypatch.setattr(articles, "extract", extract)
    result = articles.retrieve("https://example.com/news")
    if kind == "long":
        assert result.status == "excerpt" and len(result.text) == articles.MAX_TEXT
    else:
        assert not result.text and result.status == "unavailable"
    assert "private parser payload" not in result.note


def test_redirect_target_is_checked_and_fails_safely(monkeypatch):
    # Exercise actual public-IP validation at the redirected request boundary.
    calls = []
    def robots(url, deadline):
        calls.append(url)
        return True
    real_request = articles.request_page
    def request(url, deadline):
        if url == "https://example.com/news":
            return 302, {"location": "http://127.0.0.1/private"}, b""
        return real_request(url, deadline)
    monkeypatch.setattr(articles, "robots_allowed", robots)
    monkeypatch.setattr(articles, "request_page", request)
    monkeypatch.setattr(articles.socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("127.0.0.1", 80))])
    connect = Mock()
    monkeypatch.setattr(articles.socket, "create_connection", connect)
    result = articles.retrieve("https://example.com/news")
    assert not result.text and "Non-public" in result.note
    assert calls == ["https://example.com/news", "http://127.0.0.1/private"]
    connect.assert_not_called()


def test_url_cache_persists_across_instances_and_expires(article_cache, monkeypatch, restore_get):
    result = ArticleText(text="Publisher article text", status="article_text", note="Test",
                         retrieved_at=datetime.now(timezone.utc))
    fetch = Mock(return_value=result)
    first = ArticleRetriever(article_cache, ttl=100, fetch=fetch)
    monkeypatch.setattr("mehrkat.cache.time.time", lambda: 100)
    assert first.get("https://example.com/news?utm_source=test").text == result.text
    second = ArticleRetriever(article_cache, ttl=100, fetch=fetch)
    assert second.get("https://example.com/news").text == result.text
    assert fetch.call_count == 1
    monkeypatch.setattr("mehrkat.cache.time.time", lambda: 201)
    second.get("https://example.com/news")
    assert fetch.call_count == 2


def test_negative_cache_preserves_original_evidence(article_cache, evidence, restore_get):
    fetch = Mock(return_value=ArticleText(note="Blocked", retrieved_at=datetime.now(timezone.utc)))
    retriever = ArticleRetriever(article_cache, fetch=fetch)
    enriched = retriever.enrich(evidence)
    assert enriched.articles[0].evidence_text == evidence.articles[0].evidence_text
    assert enriched.articles[0].content_status == "search_evidence"
    assert enriched.articles[1].content_status == "metadata_only"
    assert all(a.retrieval_note == "Blocked" for a in enriched.articles)
    retriever.enrich(evidence)
    assert fetch.call_count == 2  # One per URL, not one per enrichment.


def test_cached_article_reused_after_discovery_expiry(settings, client, restore_get):
    result = ArticleText(text="Retrieved article fixture " * 20, status="article_text", note="Test",
                         retrieved_at=datetime.now(timezone.utc))
    service = NewsService(settings, client)
    fetch = Mock(return_value=result)
    service.articles = ArticleRetriever(service.cache, fetch=fetch)
    first = service.run(SAMPLE[0], 48)
    assert first.discovery.articles[0].content_status == "article_text"
    assert first.discovery.articles[0].search_evidence_text.startswith("Fictional")
    assert "Retrieved article fixture" in client.responses.parse.call_args.kwargs["input"]
    second = service.run(SAMPLE[0], 48)
    assert second.summary_cached
    assert fetch.call_count == 2
    with service.cache.connect() as db:
        db.execute("UPDATE cache SET expires=0 WHERE key LIKE 'discovery:%'")
    service.run(SAMPLE[0], 48)
    assert fetch.call_count == 2
    assert client.responses.create.call_count == 2


def test_article_content_changes_summary_hash(evidence):
    before = content_key(evidence.model_dump(mode="json"))
    article = evidence.articles[0]
    article.evidence_text = "Retrieved article text"
    article.content_status = "article_text"
    assert before != content_key(evidence.model_dump(mode="json"))


@pytest.mark.parametrize("mode", ["declared_size", "stream_size", "compression"])
def test_transport_enforces_download_limits(monkeypatch, mode):
    monkeypatch.setattr(articles, "public_address", lambda url: (articles.urlsplit(url), "93.184.216.34"))
    sock = Mock()
    monkeypatch.setattr(articles.socket, "create_connection", lambda *a, **k: sock)
    connection = Mock()
    monkeypatch.setattr(articles.http.client, "HTTPConnection", lambda *a, **k: connection)
    response = connection.getresponse.return_value
    response.status = 200
    response.getheaders.return_value = {
        "declared_size": [("Content-Length", str(articles.MAX_BYTES + 1))],
        "stream_size": [],
        "compression": [("Content-Encoding", "gzip")],
    }[mode]
    response.read1.return_value = b"x" * (articles.MAX_BYTES + 1)
    with pytest.raises(RetrievalError):
        articles.request_page("http://example.com/news", articles.monotonic() + 8)
    connection.close.assert_called_once()


def test_expired_failure_can_upgrade_search_evidence(article_cache, evidence, monkeypatch, restore_get):
    failed = ArticleText(note="Unavailable", retrieved_at=datetime.now(timezone.utc))
    retrieved = ArticleText(text="Recovered article", status="article_text", note="Test",
                            retrieved_at=datetime.now(timezone.utc))
    fetch = Mock(side_effect=[failed, failed, retrieved, retrieved])
    retriever = ArticleRetriever(article_cache, ttl=86400, fetch=fetch)
    monkeypatch.setattr("mehrkat.cache.time.time", lambda: 100)
    first = retriever.enrich(evidence)
    assert first.articles[0].content_status == "search_evidence"
    monkeypatch.setattr("mehrkat.cache.time.time", lambda: 1001)
    second = retriever.enrich(evidence)
    assert second.articles[0].content_status == "article_text"
    assert fetch.call_count == 4


def test_briefing_budget_does_not_discard_cached_text(article_cache, evidence, monkeypatch, restore_get):
    result = ArticleText(text="A" * 500, status="article_text", note="Test",
                         retrieved_at=datetime.now(timezone.utc))
    fetch = Mock(return_value=result)
    retriever = ArticleRetriever(article_cache, fetch=fetch)
    monkeypatch.setattr(articles, "MAX_BRIEFING_TEXT", 300)
    enriched = retriever.enrich(evidence)
    assert enriched.articles[0].content_status == "excerpt"
    assert len(enriched.articles[0].evidence_text) == 300
    assert enriched.articles[1].content_status == "metadata_only"
    assert retriever.get(str(evidence.articles[1].url)).text == "A" * 500
    assert fetch.call_count == 2


@pytest.mark.parametrize("path,rules,allowed", [
    ("/news/story", "Disallow: /news/*", False),
    ("/restricted/story", "Allow: /\nDisallow: /restricted/", False),
    ("/restricted/story", "Disallow: /restricted/\nAllow: /", False),
    ("/news/public/story", "Disallow: /news/*\nAllow: /news/public/", True),
    ("/news/public/story", "Allow: /news/public/\nDisallow: /news/*", True),
    ("/news/story", "Disallow: /news/story\nAllow: /news/story", True),
    ("/report.pdf", "Disallow: /*.pdf$", False),
    ("/report.pdf/notes", "Disallow: /*.pdf$", True),
])
def test_robots_wildcards_and_longest_match(monkeypatch, path, rules, allowed):
    body = ("User-agent: *\n" + rules).encode()
    monkeypatch.setattr(articles, "request_page", lambda *a: (200, {}, body))
    assert articles.robots_allowed("https://example.com" + path, 1) is allowed


@pytest.mark.parametrize("rules,path", [
    ("Disallow: /news/*", "/news/story"),
    ("Allow: /\nDisallow: /restricted/", "/restricted/story"),
])
def test_disallowed_articles_are_not_downloaded_and_use_search_fallback(
        monkeypatch, article_cache, evidence, restore_get, rules, path):
    requested = []
    def request(url, deadline):
        requested.append(url)
        assert url == "https://example.com/robots.txt"
        return 200, {}, ("User-agent: *\n" + rules).encode()
    monkeypatch.setattr(articles, "request_page", request)
    original = evidence.articles[0]
    evidence.articles = [original.model_copy(update={"url": "https://example.com" + path})]
    retriever = ArticleRetriever(article_cache)
    result = retriever.enrich(evidence)
    assert requested == ["https://example.com/robots.txt"]
    assert result.articles[0].evidence_text == original.evidence_text
    assert result.articles[0].content_status == "search_evidence"
    assert "Robots policy" in result.articles[0].retrieval_note


def test_old_parser_cache_entries_are_not_reused(article_cache, restore_get):
    url = "https://example.com/news/story"
    old_result = ArticleText(text="Previously cached article", status="article_text", note="Test",
                             retrieved_at=datetime.now(timezone.utc))
    article_cache.put("article:" + content_key([url, "article-v1"]),
                      old_result.model_dump(mode="json"), 86400)
    denied = ArticleText(note="Robots policy disallows retrieval.", retrieved_at=datetime.now(timezone.utc))
    fetch = Mock(return_value=denied)
    assert not ArticleRetriever(article_cache, fetch=fetch).get(url).text
    fetch.assert_called_once_with(url)


@pytest.mark.parametrize("directive", ["Crawl-delay: 0.5", "Request-rate: 10/1m"])
def test_protego_preserves_pacing_fallback(monkeypatch, directive):
    body = ("User-agent: Mehrkat\n" + directive).encode()
    monkeypatch.setattr(articles, "request_page", lambda *a: (200, {}, body))
    assert not articles.robots_allowed("https://example.com/news", 1)
