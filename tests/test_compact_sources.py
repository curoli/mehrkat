from datetime import datetime, timezone
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from mehrkat.app import create_app
from mehrkat.articles import ArticleRetriever, ArticleText


class SourceMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.buttons = []
        self.popups = {}
        self.current_link = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "a":
            self.current_link = {"attributes": attrs, "text": ""}
            self.links.append(self.current_link)
        elif tag == "button":
            self.buttons.append(attrs)
        elif "popover" in attrs:
            self.popups[attrs["id"]] = attrs

    def handle_data(self, text):
        if self.current_link is not None:
            self.current_link["text"] += text

    def handle_endtag(self, tag):
        if tag == "a":
            self.current_link = None


@pytest.mark.parametrize("status,label,explanation", [
    ("article_text", "full or partial download", "without reaching our text-length limits"),
    ("excerpt", "full or partial download", "then truncated it to fit our text-length limits"),
    ("search_evidence", "search summary", "These are not the publisher's article text"),
])
@pytest.mark.parametrize("title", ["A source title <script>test</script>", None])
def test_compact_source_links_and_explanations(settings, client, response_data, monkeypatch,
                                               status, label, explanation, title):
    response_data["output"][1]["content"][0]["annotations"][0]["title"] = title
    monkeypatch.setattr(ArticleRetriever, "get", lambda self, url: ArticleText(
        text="" if status == "search_evidence" else "Test article body never included in the result",
        status="unavailable" if status == "search_evidence" else status,
        note="Example retrieval reason", retrieved_at=datetime.now(timezone.utc),
    ))
    app = TestClient(create_app(settings, client))
    result = app.post("/api/summary?key=NASDAQ:AAPL").json()
    html = app.get("/result", params={"briefing": result["result_id"]}).text
    markup = SourceMarkup(html)
    publisher_links = [link for link in markup.links if link["attributes"]["href"] == "https://example.com/news"]
    assert publisher_links and all(link["text"] == (title or "https://example.com/news") for link in publisher_links)
    cached = [link for link in markup.links if link["attributes"]["href"].startswith("/sources/")]
    assert len(cached) == 1 and cached[0]["text"] == "(cached)"
    assert app.get(cached[0]["attributes"]["href"]).status_code == 200
    help_buttons = [button for button in markup.buttons if "popovertarget" in button and button.get("popovertargetaction") != "hide"]
    assert len(help_buttons) == 1
    button = help_buttons[0]
    assert button["type"] == "button" and button["aria-label"].startswith("Explain coverage for ")
    popup = markup.popups[button["popovertarget"]]
    assert popup["popover"] == "auto" and popup["role"] == "dialog"
    assert popup["aria-labelledby"] in html
    assert any(b.get("popovertargetaction") == "hide" and b["popovertarget"] == popup["id"] for b in markup.buttons)
    assert label in html and explanation in html
    assert "no new download or OpenAI request" in html
    assert "Publication dates are unknown/unverified" in html
    assert "Search coverage is not exhaustive" in html
    assert "Untruncated extraction does not prove complete article coverage." in html
    assert "Example retrieval reason" in html
    assert "Evidence &amp; coverage" not in html
    assert "View text used" not in html
    assert "<script>test</script>" not in html
    assert "Test article body never included in the result" not in html


def test_each_source_has_a_distinct_popup(settings, client, briefing):
    # Turn the second fixture source into cited search evidence, keeping source IDs stable.
    from mehrkat.models import RelevanceDecision
    original_response = client.responses.create.return_value.model_dump()
    part = original_response["output"][1]["content"][0]
    claim = "Another fictional finding. "
    part["text"] += "\n\n" + claim
    start = len(part["text"])
    part["text"] += "[2]"
    part["annotations"].append({
        "type": "url_citation", "url": "https://example.com/metadata", "title": "Second source",
        "start_index": start, "end_index": len(part["text"]),
    })
    second_id = briefing.relevance[1].article_id
    briefing.relevance[1] = RelevanceDecision(article_id=second_id, category="direct", reason="Test")
    briefing.developments[0].source_ids.append(second_id)
    app = TestClient(create_app(settings, client))
    assert app.post("/api/summary?key=NASDAQ:AAPL").status_code == 200
    markup = SourceMarkup(app.get("/result").text)
    buttons = [b for b in markup.buttons if "popovertarget" in b and b.get("popovertargetaction") != "hide"]
    assert len(buttons) == 2
    assert len({b["popovertarget"] for b in buttons}) == 2
    assert all(b["popovertarget"] in markup.popups for b in buttons)
