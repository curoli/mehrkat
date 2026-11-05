from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, computed_field


class Listing(BaseModel):
    listing_key: str
    ticker: str
    exchange: str
    name: str
    country: str = ""
    asset_type: str = "Stock"
    sector: str = ""
    aliases: list[str] = Field(default_factory=list)
    isin: str | None = None


class Evidence(BaseModel):
    id: str
    url: HttpUrl
    title: str | None = None
    published_at: datetime | None = None
    published_at_verified: bool = False
    retrieved_at: datetime
    evidence_text: str = ""
    content_status: Literal["search_evidence", "metadata_only", "article_text", "excerpt"]
    search_evidence_text: str | None = None
    retrieval_note: str | None = None
    text_retrieved_at: datetime | None = None
    text_url: str | None = None


class Discovery(BaseModel):
    listing_key: str
    window_start: datetime
    window_end: datetime
    discovered_at: datetime
    articles: list[Evidence]
    limitations: list[str]


class RelevanceDecision(BaseModel):
    article_id: str
    category: Literal["direct", "indirect", "uncertain", "irrelevant"]
    reason: str


class Development(BaseModel):
    title: str
    factual_summary: str
    possible_implications: str | None
    source_ids: list[str]


class StockBriefing(BaseModel):
    overview: str
    developments: list[Development]
    relevance: list[RelevanceDecision]
    insufficient_news: bool
    limitations: list[str]


class CoverageStats(BaseModel):
    evaluated_sources: int
    used_articles: int
    full_text_articles: int = Field(description="Non-truncated extracted text; completeness unverified")
    excerpt_articles: int
    search_summary_articles: int


class SummaryResult(BaseModel):
    listing: Listing
    discovery: Discovery
    briefing: StockBriefing
    generated_at: datetime
    discovery_cached: bool
    summary_cached: bool


    @computed_field
    @property
    def coverage(self) -> CoverageStats:
        used_ids = {source_id for event in self.briefing.developments for source_id in event.source_ids}
        used = [article for article in self.discovery.articles if article.id in used_ids]
        return CoverageStats(
            evaluated_sources=len(self.discovery.articles),
            used_articles=len(used),
            full_text_articles=sum(article.content_status == "article_text" for article in used),
            excerpt_articles=sum(article.content_status == "excerpt" for article in used),
            search_summary_articles=sum(article.content_status == "search_evidence" for article in used),
        )

    @property
    def coverage_notes(self) -> list[str]:
        # Coverage facts come from retrieval metadata. Model-written caveats
        # remain available in Debug rather than repeating these facts in the UI.
        seen = set()
        notes = []
        for note in self.discovery.limitations:
            key = " ".join(note.casefold().split()).rstrip(".")
            if key and key not in seen:
                seen.add(key)
                notes.append(note.strip())
        return notes
