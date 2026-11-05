# Architecture

Browser → FastAPI/Jinja2 → local listing directory → selected listing.
Only an explicit POST starts the paid workflow:

1. Discovery cache lookup → OpenAI Responses web_search on miss.
2. Parse native consulted-source URLs and inline citation spans into evidence.
3. Summary cache lookup → separate Responses Structured Outputs call on miss.
4. Validate source IDs/relevance and render cited developments in Jinja2.

No articles are crawled. Evidence strings are model-written search claims,
not verbatim snippets or full article texts. Native source metadata establishes
where links came from, not whether the claims are true.

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
refresh it. Default TTL: 900 seconds. Summary keys hash exact serialized discovery
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
