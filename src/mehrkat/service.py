from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from openai import OpenAI

from . import discovery, summarization
from .cache import Cache, content_key
from .models import Discovery, StockBriefing, SummaryResult


class NewsService:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self.cache = Cache(settings.cache_path)
        self.lock = Lock()
        self.metrics = dict(requests=0, discovery_hits=0, discovery_misses=0,
                            summary_hits=0, summary_misses=0, failures=0,
                            last_duration_seconds=None, last_successful_refresh=None)
        self.last_result = None
        self.phase = "idle"

    def run(self, listing, hours):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("Another briefing is running. Please wait and retry.")
        started = monotonic()
        self.metrics["requests"] += 1
        try:
            if not self.settings.api_key and self.client is None:
                raise ValueError("Set OPENAI_API_KEY in the project .env file or environment, then restart the app.")
            if self.client is None:
                self.client = OpenAI(api_key=self.settings.api_key, timeout=60, max_retries=1)
            now = datetime.now(timezone.utc)
            key = "discovery:" + content_key([listing.model_dump(), hours, discovery.VERSION, self.settings.discovery_model, "medium", 2])
            self.phase = "searching"
            saved = self.cache.get(key)
            discovery_hit = saved is not None
            self.metrics["discovery_hits" if discovery_hit else "discovery_misses"] += 1
            if saved:
                evidence = Discovery.model_validate(saved)
            else:
                evidence = discovery.discover(self.client, self.settings.discovery_model, listing, now - timedelta(hours=hours), now)
                self.cache.put(key, evidence.model_dump(mode="json"), self.settings.discovery_ttl)
                self.metrics["last_successful_refresh"] = now.isoformat()
            self.phase = "summarizing"
            skey = "summary:" + content_key([listing.model_dump(), evidence.model_dump(mode="json"), self.settings.summary_model, summarization.VERSION])
            saved = self.cache.get(skey)
            summary_hit = saved is not None
            self.metrics["summary_hits" if summary_hit else "summary_misses"] += 1
            if saved:
                briefing = StockBriefing.model_validate(saved["briefing"])
                generated = datetime.fromisoformat(saved["generated_at"])
            else:
                briefing = summarization.summarize(self.client, self.settings.summary_model, listing, evidence)
                generated = datetime.now(timezone.utc)
                self.cache.put(skey, {"briefing": briefing.model_dump(mode="json"), "generated_at": generated.isoformat()}, 86400)
            result = SummaryResult(listing=listing, discovery=evidence, briefing=briefing, generated_at=generated,
                                   discovery_cached=discovery_hit, summary_cached=summary_hit)
            self.last_result = result
            return result
        except Exception:
            self.metrics["failures"] += 1
            raise
        finally:
            self.phase = "idle"
            self.metrics["last_duration_seconds"] = round(monotonic() - started, 2)
            self.lock.release()
