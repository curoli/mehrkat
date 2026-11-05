# Architecture

Browser → FastAPI/Jinja2 → local listing directory → selected listing.
Only an explicit POST starts the paid workflow:

1. Discovery cache lookup → OpenAI Responses web_search on miss.
2. Parse native consulted-source URLs and inline citation spans into evidence.
3. Attempt article extraction for each discovered source URL, reusing a separate URL cache.
4. Summary cache lookup → separate Responses Structured Outputs call on miss.
5. Validate source IDs/relevance and render cited developments in Jinja2.

Discovery initially produces model-written cited search claims. A narrow retriever
then attempts public HTML article extraction from each source URL. Extracted text
replaces the search claim as the primary evidence when available; the original
claim remains attached for provenance. Retrieval failure leaves search evidence
unchanged. Metadata-only sources become usable only if text is actually extracted.
Native source metadata establishes where links came from, not whether claims are
true. Extraction completeness is not independently established.

## API

- GET /: HTML search UI; GET /api/listings?q=: up to 25 typed listing results.
- GET /listing?key=: exact upstream listing-key selection.
- POST /api/summary?key=&hours=: typed listing, evidence, briefing, times and cache status.
- GET /result: latest process-local result; GET /api/status: current phase.
- GET /settings, /monitoring, /debug: separate ancillary views.
- GET /health: process health, not an upstream availability check.

Query parameters support punctuation in listing keys without path ambiguity.
The browser uses textContent for search results; Jinja autoescapes output.
Only HTTP(S) links without embedded credentials are accepted.

## Caches

SQLite stores JSON and expiry. Discovery keys hash canonical listing metadata,
lookback hours, discovery model/prompt version, context size and tool budget.
A cache hit retains the original requested UTC window; it does not pretend to
refresh it. Default TTL: 900 seconds. Summary keys hash exact serialized enriched
evidence, listing metadata, summary model and English prompt/schema version.
Summary TTL: one day. A summary model change reuses discovery.
Expired entries are pruned on writes. Settings and API keys are never serialized.

The evidence hash includes retrieval times, so refreshed discovery generally
invalidates the summary even when claims look similar. This deliberately favors
clear provenance over maximal reuse.

## Scaling

This local, single-user application uses synchronous SDK calls in FastAPI's
threadpool, short SQLite connections, and one nonblocking process lock to bound
concurrent paid workflows. Status polling remains responsive. Multiple workers
would need distributed deduplication, per-user result IDs, shared cache/metrics,
authentication, rate limits and spending controls. Queues/jobs and streaming
could support longer research later; they are unnecessary for this exercise.

## Article text retrieval and caching

Article cache keys hash conservative canonical URLs plus extractor version, and
are independent of company/listing identity. Successful extractions persist for
ARTICLE_CACHE_TTL_SECONDS (default 86400); failures are cached for up to 900
seconds, then retried. Cached retrieval timestamps remain stable, allowing summary
reuse. Content changes or an upgrade from fallback to article text changes the
summary hash. Article caches are consulted even when discovery is cached; refreshing
discovery does not download unexpired article text again.

At most four source retrievals run concurrently. Each source has an eight-second
network deadline (DNS resolution uses the operating system's resolver timeout),
up to three redirects, a 2 MB HTML limit and a 30,000-character extracted-text cap.
Summarization receives at most 120,000 extracted article characters across sources;
excess text is truncated or replaced by its search fallback without deleting the
cached extraction. These are explicit bounded excerpts, not verified full text.
Public destinations are resolved and validated before connecting directly to a
validated numeric IP, preserving TLS hostname verification and preventing DNS
rebinding. Redirects repeat destination and robots checks. No publisher cookies,
API keys, authentication headers, or environment proxy configuration are used.
The application does not execute JavaScript.

Trafilatura extracts article text, excluding comments. Publisher HTML and raw
responses are not cached. Full bodies are excluded from the summary HTTP response,
result HTML and debug page; the model and local SQLite cache receive the extracted
text. UI/API metadata reports extraction status, retrieval time and fallback reason.
