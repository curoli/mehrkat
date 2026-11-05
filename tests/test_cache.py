from mehrkat.cache import Cache, content_key
from mehrkat.listings import SAMPLE
from mehrkat.service import NewsService


def test_ttl(settings, monkeypatch):
    cache = Cache(settings.cache_path)
    monkeypatch.setattr("mehrkat.cache.time.time", lambda: 100)
    cache.put("test", {"value": 1}, 10)
    assert cache.get("test") == {"value": 1}
    monkeypatch.setattr("mehrkat.cache.time.time", lambda: 111)
    assert cache.get("test") is None


def test_independent_caches(settings, client):
    service = NewsService(settings, client)
    first = service.run(SAMPLE[0], 48)
    second = service.run(SAMPLE[0], 48)
    assert not first.discovery_cached and not first.summary_cached
    assert second.discovery_cached and second.summary_cached
    assert client.responses.create.call_count == 1
    assert client.responses.parse.call_count == 1
    settings.summary_model = "changed-model"
    third = service.run(SAMPLE[0], 48)
    assert third.discovery_cached and not third.summary_cached
    assert client.responses.create.call_count == 1
    assert client.responses.parse.call_count == 2
    with service.cache.connect() as db:
        db.execute("UPDATE cache SET expires=0 WHERE key LIKE 'discovery:%'")
    service.run(SAMPLE[0], 48)
    assert client.responses.create.call_count == 2


def test_evidence_content_changes_key(evidence):
    before = content_key(evidence.model_dump(mode="json"))
    evidence.articles[0].evidence_text += "changed"
    assert before != content_key(evidence.model_dump(mode="json"))


def test_credentials_not_cached(settings, client):
    settings.api_key = "fixture-secret-do-not-store"
    NewsService(settings, client).run(SAMPLE[0], 48)
    assert b"fixture-secret-do-not-store" not in settings.cache_path.read_bytes()


def test_summary_schema_version_change_reuses_discovery(settings, client, monkeypatch):
    service = NewsService(settings, client)
    service.run(SAMPLE[0], 48)
    monkeypatch.setattr("mehrkat.summarization.VERSION", "fixture-new-schema-version")
    result = service.run(SAMPLE[0], 48)
    assert result.discovery_cached and not result.summary_cached
    assert client.responses.create.call_count == 1
    assert client.responses.parse.call_count == 2
