"""Best-effort public article extraction, URL cache and search-evidence fallback."""
import http.client
import ipaddress
import re
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic
from typing import Literal
from urllib.parse import quote, urljoin, urlsplit

from protego import Protego
from pydantic import BaseModel
from trafilatura import extract
from trafilatura.settings import use_config

from .cache import content_key
from .discovery import canonical_url

VERSION = "article-v2-robots"
USER_AGENT = "Mehrkat/0.1"
MAX_BYTES = 2_000_000
MAX_TEXT = 30_000
MAX_BRIEFING_TEXT = 120_000
TIMEOUT = 8


class RetrievalError(Exception):
    """Fixed, user-safe reason; never include response bodies or request headers."""


class ArticleText(BaseModel):
    text: str = ""
    status: Literal["unavailable", "article_text", "excerpt"] = "unavailable"
    note: str
    retrieved_at: datetime
    final_url: str | None = None


def public_address(url):
    parts = urlsplit(url)
    if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username
            or parts.password or parts.port not in {None, 80, 443}):
        raise RetrievalError("Unsupported article URL.")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    ips = {entry[4][0] for entry in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise RetrievalError("Non-public network destination blocked.")
    return parts, sorted(ips)[0]


def request_page(url, deadline):
    # Connect to the validated numeric IP: a second DNS lookup cannot rebind
    # the request to a private address. TLS still checks the original hostname.
    parts, address = public_address(url)
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise RetrievalError("Article retrieval timed out.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    connection = http.client.HTTPConnection(parts.hostname, port, timeout=remaining)
    sock = socket.create_connection((address, port), timeout=remaining)
    try:
        if parts.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
        connection.sock = sock
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parts.query:
            path += "?" + quote(parts.query, safe="=&%/:?@!$'()*+,;~-._")
        connection.request("GET", path, headers={"User-Agent": USER_AGENT,
                           "Accept": "text/html,text/plain;q=0.9", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        headers = {k.lower(): v for k, v in response.getheaders()}
        if response.status != 200:
            return response.status, headers, b""
        if headers.get("content-encoding", "identity").lower() != "identity":
            raise RetrievalError("Unsupported response compression.")
        if int(headers.get("content-length", "0")) > MAX_BYTES:
            raise RetrievalError("Article exceeds download size limit.")
        chunks = []
        size = 0
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RetrievalError("Article retrieval timed out.")
            sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                raise RetrievalError("Article exceeds download size limit.")
        return response.status, headers, b"".join(chunks)
    finally:
        connection.close()
        sock.close()


def robots_allowed(url, deadline):
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    status, _, body = request_page(robots_url, deadline)
    if status == 404:
        return True
    if status != 200:
        # Fail closed on unavailable robots or redirects; no access workarounds.
        return False
    parser = Protego.parse(body.decode("utf-8", errors="replace"))
    if parser.crawl_delay(USER_AGENT) or parser.request_rate(USER_AGENT):
        return False  # This small retriever does not implement publisher pacing.
    return parser.can_fetch(url, USER_AGENT)


def retrieve(url):
    deadline = monotonic() + TIMEOUT
    try:
        current = url
        for _ in range(4):
            # Every redirect target gets a fresh robots and public-IP check.
            if not robots_allowed(current, deadline):
                raise RetrievalError("Robots policy disallows retrieval or could not be checked.")
            status, headers, body = request_page(current, deadline)
            if status in {301, 302, 303, 307, 308} and headers.get("location"):
                target = canonical_url(urljoin(current, headers["location"]))
                if target is None:
                    raise RetrievalError("Unsupported redirect destination.")
                current = target
                continue
            if status != 200:
                raise RetrievalError("Publisher page unavailable or access restricted.")
            if headers.get("content-type", "").split(";")[0].strip().lower() not in {"text/html", "application/xhtml+xml"}:
                raise RetrievalError("Only HTML articles are supported.")
            # Honor explicit free-access metadata. Never attempt login, consent,
            # alternate AMP pages, or paywall removal.
            if re.search(rb'["\']isAccessibleForFree["\']\s*:\s*(?:false|["\']false["\'])', body, re.I):
                raise RetrievalError("Publisher marks this content as restricted.")
            extraction_config = use_config()
            extraction_config.set("DEFAULT", "MAX_TREE_SIZE", "100000")
            extraction_config.set("DEFAULT", "MAX_FILE_SIZE", str(MAX_BYTES))
            text = extract(body, url=current, include_comments=False, include_tables=True,
                           favor_precision=True, config=extraction_config)
            if not text or len(text.strip()) < 200:
                raise RetrievalError("No substantial article text could be extracted.")
            text = text.strip()
            if re.search(r"subscribe to (?:continue|read)|sign in to (?:continue|read)|"
                         r"accept (?:all )?cookies to|enable javascript to", text, re.I):
                raise RetrievalError("Article appears to require subscription, consent or JavaScript.")
            truncated = len(text) > MAX_TEXT
            return ArticleText(text=text[:MAX_TEXT], status="excerpt" if truncated else "article_text",
                               note="Extracted article text; completeness unverified." if not truncated
                               else "Extracted text truncated to 30,000 characters.",
                               retrieved_at=datetime.now(timezone.utc), final_url=current)
        raise RetrievalError("Too many article redirects.")
    except RetrievalError as exc:
        note = str(exc)
    except Exception:
        # Retrieval is optional; isolate transport/parser failures without
        # revealing provider content or preventing the search-evidence fallback.
        note = "Article retrieval or extraction failed."
    return ArticleText(note=note, retrieved_at=datetime.now(timezone.utc))


class ArticleRetriever:
    def __init__(self, cache, ttl=86400, fetch=retrieve):
        self.cache = cache
        self.ttl = ttl
        self.fetch = fetch

    def get(self, url):
        canonical = canonical_url(url)
        if canonical is None:
            return ArticleText(note="Unsupported article URL.", retrieved_at=datetime.now(timezone.utc))
        key = "article:" + content_key([canonical, VERSION])
        saved = self.cache.get(key)
        if saved is not None:
            return ArticleText.model_validate(saved)
        result = self.fetch(canonical)
        # Successful text lasts a day by default; retry failures after 15 min.
        self.cache.put(key, result.model_dump(mode="json"), self.ttl if result.text else min(self.ttl, 900))
        return result

    def enrich(self, discovery):
        def enrich_article(article):
            result = self.get(str(article.url))
            updates = dict(retrieval_note=result.note, text_retrieved_at=result.retrieved_at,
                           text_url=result.final_url)
            if result.text:
                updates.update(search_evidence_text=article.evidence_text,
                               evidence_text=result.text, content_status=result.status)
            return article.model_copy(update=updates)

        # Bounded concurrency; each source failure independently falls back.
        with ThreadPoolExecutor(max_workers=4) as pool:
            articles = list(pool.map(enrich_article, discovery.articles))
        # Cache each extraction independently, but bound model input across
        # many sources. Preserve discovery order and the original fallback.
        remaining = MAX_BRIEFING_TEXT
        for index, article in enumerate(articles):
            if article.content_status not in {"article_text", "excerpt"}:
                continue
            if remaining < 200:
                original = discovery.articles[index]
                articles[index] = article.model_copy(update={
                    "evidence_text": original.evidence_text, "content_status": original.content_status,
                    "retrieval_note": "Text cached, but search findings used because the briefing text budget was reached.",
                })
                continue
            if len(article.evidence_text) > remaining:
                articles[index] = article.model_copy(update={
                    "evidence_text": article.evidence_text[:remaining], "content_status": "excerpt",
                    "retrieval_note": "Extracted text truncated to fit the briefing text budget.",
                })
            remaining -= min(len(article.evidence_text), remaining)
        return discovery.model_copy(update={"articles": articles, "limitations": [
            "Article text was attempted for each source. Where retrieval failed, cited search findings are used.",
            "Extracted text may be incomplete; long text is explicitly labelled as an excerpt. Search coverage is not exhaustive.",
            "Publication dates are not independently verified; the requested interval is not a guaranteed hard filter.",
        ]})
