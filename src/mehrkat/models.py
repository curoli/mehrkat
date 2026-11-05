from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


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


class SummaryResult(BaseModel):
    listing: Listing
    discovery: Discovery
    briefing: StockBriefing
    generated_at: datetime
    discovery_cached: bool
    summary_cached: bool
