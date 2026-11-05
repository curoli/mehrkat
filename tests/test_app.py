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
