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
- GET /result?briefing=: a saved briefing snapshot (omitting the ID shows the latest process-local result).
- GET /sources/{result_id}/{source_id}: exact cached evidence for a cited source.
- GET /api/status: current phase.
- GET /settings, /monitoring, /debug: separate ancillary views.
- GET /health: process health, not an upstream availability check.

Query parameters support punctuation in listing keys without path ambiguity.
The browser uses textContent for search results; Jinja autoescapes output.
Only HTTP(S) links without embedded credentials are accepted.

## Caches

SQLite stores JSON and expiry. Discovery keys hash canonical listing metadata,
lookback hours, discovery model/prompt version, context size, output/tool budgets,
maximum candidate sources and maximum search passes.
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
briefing HTML and debug page by default; the model and local SQLite cache receive
the extracted text. An explicit (cached) link opens the cited source's cached
evidence on a separate page. UI/API metadata reports extraction status, retrieval time and fallback reason.


## Optional listing filters

The search page offers checkbox groups for exchanges, countries and sectors,
populated from the directory loaded at startup. Empty groups impose no restriction.
Multiple selections within a group are alternatives (OR); selected groups must
all match (AND). Matching ignores case and extra whitespace. A text query can be
combined with filters, or filters alone can browse listings. With neither text nor
filters, results stay empty. Filtering happens before ranking and the 25-row cap.
Missing metadata does not match a selected value.

GET /api/listings accepts repeated exchange, country and sector parameters, e.g.
`/api/listings?q=SAP&exchange=NYSE&exchange=XETRA&country=Germany`.
Filter values and the text query travel in URLs through listing and briefing
navigation, so return links restore the search. Clear filters retains the text
query. These are local directory filters only; they do not restrict news sources
or change the selected company's summarization context.

## Briefing coverage statistics

SummaryResult computes coverage from unique source IDs cited by developments,
not model-generated counts. Reusing one source for several events counts once.
The UI/API reports articles used, non-truncated article extractions, excerpts,
search-summary fallbacks, and the total sources evaluated. Uncited extractions
do not inflate the full-text count; insufficient-news results cite zero articles.
“Full text extracted” means the extractor returned article text without configured
truncation, not independently verified completeness.

The result page shows a compact count line and per-source explanations instead
of a separate Evidence & coverage section. Counts remain available in the API.
Each source's question-mark popup explains the actual input type, truncation or
fallback, date uncertainty, incomplete coverage and the cached-text viewer.
Model-written limitations remain in the API's briefing and Debug page.

Robots matching uses [Protego](https://github.com/scrapy/protego) for wildcard
rules, end anchors and longest-match precedence (allow wins an equal-length tie).
The application still handles robots HTTP failures and redirects conservatively
and skips publishers requiring request pacing. The article cache version changes
with this parser correction so entries obtained under the earlier parser are
not reused.

Each filter summary shows its selected-option count, including while collapsed.
Counts and reset-button availability are rendered from normalized selections and
updated immediately on checkbox changes. Each group has its own reset button,
visible even while collapsed; it clears only that group and refreshes results
while preserving the text query and other groups. The existing Clear filters
button still clears all groups. Empty groups show zero and disable their reset.

## Source list and exact evidence snapshots

The result page lists unique sources cited in developments in compact rows:
the title links to the original publisher URL (using the URL as link text when
the title is absent), followed by a (cached) evidence-view link, a short coverage
label and a question-mark explanation button. Downloads use “full or partial
download”; generated search findings use “search summary”. Development citations
retain direct publisher links without repeating long coverage metadata.
Uncited discovery candidates are excluded from this list.

Successful workflows save a result snapshot containing the enriched, budget-limited
evidence alongside the briefing. Its stable ID hashes the summary cache key and
generation time. Repeated cached generations share an ID; different evidence gets a
different ID. The browser navigates to that ID and carries search/filter state
through source-view and return links, so another generation cannot replace the
text under an existing link.

Snapshots persist in SQLite for at most 24 hours, bounded by
ARTICLE_CACHE_TTL_SECONDS if that is shorter. GET /sources reads only the named
snapshot and checks that the source was cited. It never retrieves a URL or calls
OpenAI, and returns 404 for missing/expired snapshots or uncited/unknown sources.
Snapshots also work after an app restart without an API key. An expired view
does not silently substitute newer article-cache text.

The viewer autoescapes text, preserves paragraphs and whitespace, reports coverage
and retrieval times, and distinguishes the primary evidence from generated search
findings also supplied as context. These findings are not article text. Excerpts
show the exact truncation supplied to the model, not a longer URL-cache version.
Response Cache-Control: no-store prevents implicit browser retention of the text.
The ordinary summary API, briefing page and Debug page still omit source bodies.
This remains a local, single-user app; saved IDs are not authentication.

Source explanations use native HTML auto-popovers with labelled buttons and
dialogs, explicit Close controls, Escape/outside-click dismissal and one popup
open at a time. They need a browser supporting the HTML Popover API; no additional
JavaScript dependency or network request is used to show them. Explanations clarify
untruncated versus budget-truncated extraction and search-summary fallback, retain
the retrieval reason/time, and explain cache inspection, unverified dates and
non-exhaustive search coverage. The (cached) evidence route is unchanged.

## Broader news discovery

Discovery defaults to up to three complementary Responses requests: broad company
news/primary announcements, additional independent financial/operational reporting,
and supported regulatory/sector/supplier/competitor news. Each requests article-by-
article cited findings instead of a three-to-five-event summary, and asks for new
URLs beyond those already found. A fourth international/regional focus is available
when configured.

NEWS_MAX_ARTICLES defaults to 20 (bounded 1–40); DISCOVERY_SEARCH_PASSES defaults to
3 (bounded 1–4). Each pass uses high search context, at most two web-search tool
calls, and at most 6,000 output tokens. Search stops early once the candidate target
has that many citation-backed records. Consulted-source metadata alone does not
trigger early stopping. Across passes, canonical URLs are merged, evidence is
preserved/combined, and citation-backed findings are prioritized before filling
remaining slots with consulted sources. No more than the configured cap proceeds
to article retrieval and summary evaluation.

This increases cost and latency on cache misses: the default permits three
discovery API requests (up to six search tool calls) plus one summary request,
before the SDK's existing bounded retry behavior. The aggregate discovery result
is cached as before; budget changes invalidate that cache. A failing pass surfaces
an error, so a later failed pass can require earlier searches to be repeated.
Article URL caches, four-retrieval concurrency and text budgets remain unchanged.

The summary still groups sources into roughly 3–5 developments in one page.
Corroborating relevant sources may share a development; irrelevant or uncertain
sources are not cited to inflate the count. The UI shows sources evaluated versus
sources cited, including zero-citation outcomes. These are candidate sources, not
a guarantee of 20 eligible recent articles, exhaustive coverage, or 20 citations.

## Required source assessments

The provider's summary schema is specialized to the evidence set: relevance is an
object with each exact source ID as a required key, and extra keys are forbidden.
Each value contains only category and reason. A plain array schema could not
guarantee that every input ID appeared exactly once; with larger evidence sets,
a schema-valid list could omit or repeat IDs and then fail application validation.

The official SDK's parsed object is converted back into the existing public
StockBriefing.relevance list, in input-source order. Public APIs and cache formats
remain unchanged. Citation IDs, source text/relevance suitability and insufficient-
news consistency are still validated in Python. Metadata-only and irrelevant
sources must also have assessments; they are not omitted just because they are
not cited. This enforces output structure, not factual accuracy.

The normal summary remains one tool-free call. Its output allowance is 5,000
tokens plus 120 per source (up to 9,800 with the configured 40-source cap), providing
room for complete assessments as well as the briefing. Refusals, truncation and
invalid citations still fail transparently. The summary schema/prompt version
changes its cache key without invalidating discovery or article caches.
