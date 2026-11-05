# Testing

Install the dev extra and run `pytest -q` from the project root. Tests inject
temporary settings, a temporary SQLite cache, and mocked OpenAI responses. No
paid calls or network are used by pytest; the owner's .env is never copied into
fixtures. The default app loads runtime configuration on import, but test
requests use explicit key-free settings.

Tests cover local ticker/name/alias lookup, venue ambiguity, stock-only import,
native source/citation extraction, deduplication, invalid URLs, unknown dates,
required tool invocation, no tools in summary, citation/relevance rejection,
insufficient evidence, refusal, cache expiry/independence, evidence hashing,
credential exclusion, page navigation, POST workflow/clickable sources and
sanitized provider/timeout/key errors.

Event grouping, importance, source reliability and factual accuracy require human
evaluation. Fixture summaries encode intended grouping; asserting their display
does not prove a model will consistently group live coverage. Prompt changes
should be checked against several saved, permitted evidence sets.

## Manual smoke checklist

1. Launch with README commands; root shows search immediately.
2. Type SAP; choose XETRA or NYSE explicitly; details remain venue-specific.
3. Generate with a valid key; observe searching/summarizing states and citations.
4. Repeat within TTL; both cache flags show cached.
5. Inspect settings/monitoring/debug without exposing any credentials.
6. Without a key, search still works and generation gives setup instructions.
7. Review sources against overview/developments, date caveats and implications.

Live verification results are recorded below when performed.

## Verification in this implementation session

- 39 deterministic tests passed on Python 3.13.5 with OpenAI SDK 2.54.0.
  TestClient required running outside this environment's sandbox; the sandboxed
  run stalled in its event loop. No test made a real API request.
- Dependency consistency check passed. Starlette emitted a deprecation warning
  for its httpx TestClient integration; it does not affect these passing tests.
- Optional upstream download succeeded; the directory loaded 74,800 stock
  listings. Downloaded data remains ignored and is not part of the submission.
- One bounded live smoke attempt reached OpenAI but failed with RateLimitError.
  Rate-limit/quota access must be resolved before real generation can be verified.
  No successful live discovery or summarization is claimed.
- Browser behavior was checked through HTML/API integration tests, not a manual
  graphical browser session.

To repeat the explicit billable smoke check after resolving access:
`python scripts/smoke.py`. It explicitly limits discovery to one pass and
performs at most one request per stage with retries
disabled, or uses cached results; it prints counts/cache flags, never keys or
provider payloads.

Adjacent-citation regressions cover three sources supporting one claim with no
separator, spaces, tabs or a single newline. They also verify that new claim text
or a blank paragraph prevents evidence inheritance, and that all supporting IDs
pass summary validation. The full 39-test suite, including API integration tests,
passed outside the sandbox after this fix.

## Article retrieval tests

The original workflow fixtures stub ArticleRetriever.get to a deterministic
unavailable result; they never access publisher URLs. Retrieval tests use fake
HTTP responses/sockets and invented article HTML. One extraction test runs the
real Trafilatura parser against that local fixture.

Coverage includes canonical URL cache reuse across instances and discovery
refreshes, expiry, shorter failure caching and recovery, search fallback,
summary input/hash changes, metadata-only sources, extraction/truncation budgets,
robots disallow/error/pacing handling, restricted content, private-IP and mixed
DNS blocking, redirect target checks, TLS hostname preservation with IP pinning,
download/compression limits, and omission of article bodies from default briefing/API/debug
responses. No paid API calls are used by these tests.

Article-text implementation verification: 77 Python tests passed on Python 3.13.
JavaScript syntax and dependency consistency checks passed. A live, key-free
retrieval of an Apple Newsroom earnings release extracted 2,785 characters;
a repeated lookup used the local URL cache (one fetch total). This verifies an
actual download/extraction/cache path, not complete article coverage or summary
quality. No paid OpenAI request was made for this change, and no graphical browser
verification was performed. The existing Starlette/httpx deprecation warning
remains.


## Listing filter verification

Python tests cover multiple values, intersection across groups, filters without
a text query, case/whitespace normalization, empty/unknown values, missing
metadata, filtering before the result limit, directory-derived options, and
filter restoration in search, listing and briefing HTML. They also check that
filtering/navigation does not call OpenAI.

Optional JavaScript regression tests use Node.js 20+ with its built-in test
runner and DOM/fetch stubs (no npm dependencies):

```sh
node --test tests/js/*.test.cjs
```

These verify filter-only search, repeated filter parameters in listing links,
filter changes/clearing, query restoration and briefing redirects. They do not
replace a graphical browser check.

Filter restoration regressions also exercise lowercase and whitespace-padded
exchange/country/sector parameters on initial load and after listing/briefing
return navigation. The canonical checked values must produce exactly the same
API results as the original normalized request.

Coverage-statistic regressions check unique cited-source counts across repeated
citations and developments, mixed text/excerpt/search coverage, uncited sources,
zero-use insufficient-news results, normalized warning deduplication, API/HTML
statistics and cached responses. The combined branch also runs all restored
filter navigation tests, including normalization on return links.

Combined filter/coverage verification: all 91 Python tests passed, including
API integration tests outside the sandbox. The Node.js search regression file,
JavaScript syntax and diff checks passed. No paid calls or graphical browser
checks were made for the coverage changes.

Robots parser regressions cover wildcard disallows, longest-match precedence
regardless of directive order, longer allow exceptions, equal-length allow ties,
end anchors and pacing directives. Retrieval-level tests prove both reported
disallow cases fetch only robots.txt, never the article, and retain search
evidence. A cache regression checks that entries obtained using the old parser
are not reused after the cache version change.

After the robots parser fix, all 104 Python tests, the JavaScript regression
checks and dependency consistency check passed using Protego 0.7.0. No live
retrieval, paid API call or graphical browser check was performed for this fix.

Filter-control tests verify server-rendered zero/restored counts and disabled
reset buttons, including duplicate and normalized URL values. JavaScript tests
verify immediate count updates before debounced requests, per-group reset
isolation, preserved query/other filters, refreshed results and listing URLs,
and all-group reset state. All 106 Python tests, the JavaScript regression
checks, syntax and diff checks passed for this change. No API calls or graphical
browser checks were performed.

## Source evidence viewer verification

Source-view tests cover article text, excerpts and search fallbacks; unique cited
source lists with publisher URLs; exact primary and supplementary text supplied
to the summary; HTML escaping; preservation of search/filter state and a stable
briefing ID; snapshot reuse across cached generations; previous evidence surviving
new generations and process restarts; input-budget truncation; expiry; and rejection
of unknown/uncited sources. Viewing makes no article retrieval or OpenAI call.
Default result/API/debug responses remain free of source bodies.

All 113 Python tests passed for this change, plus the Node.js search/navigation
regressions, JavaScript syntax, dependency consistency and diff checks. No live
API calls or graphical browser verification were performed. The existing
TestClient deprecation warning remains.

## Compact source-list verification

All 120 Python tests passed after this change. New markup regressions cover
title/URL fallback, publisher and (cached) links, extraction/excerpt/search labels,
source-specific explanations, escaped titles, unique accessible popup targets and
Close controls, retained uncertainty/caching information, omission of source
bodies, and removal of the separate Evidence & coverage section. The existing
JavaScript regression checks and syntax/diff checks passed.

A headless Chrome smoke check against rendered fictional fixture content verified
popup opening, one-at-a-time behavior, Escape, Close, outside-click dismissal, and
fit within a 390-pixel mobile viewport. No live article or OpenAI requests were made.
The existing TestClient deprecation warning remains.

## Broader discovery verification

Dedicated multi-response mocks verify complementary query focuses, preservation
of more than four distinct articles, canonical URL deduplication and merged
evidence, metadata-to-citation upgrades, citation-backed prioritization, source
caps, early stopping, bounded pass counts, honest scarce-result handling,
transparent search errors, environment bounds, and cache invalidation when
discovery budgets change. Older workflow fixtures explicitly use one pass to
isolate their existing cache/relevance/error contracts; runtime defaults are
tested separately.

The explicit live smoke script still uses only one discovery pass plus one
summary request, with retries disabled, regardless of normal application settings.
All 134 Python tests and the JavaScript regression checks passed, along with
syntax, dependency consistency and diff checks. One bounded live discovery call
(one pass, retries disabled) returned seven distinct citation-backed candidate
sources. That check did not download article pages or generate a briefing.
The full multi-pass workflow and final summary quality were not live-verified.
The existing TestClient deprecation warning remains.

## Complete source-assessment regression

The Alphabet failure had 14 distinct cached source IDs; the invalid model response
was not retained, so its exact omission/duplication could not be reconstructed.
Synthetic cases with 14, 20 and 40 sources verify required provider-schema keys,
complete conversion to the public decision list, single tool-free summary calls
and scaled output budgets. Missing/unknown keys, duplicate input IDs and invalid
citations remain rejected. The official OpenAI SDK is also tested against an
httpx MockTransport to verify strict schema serialization and parsing. Changing
the schema version reruns summarization while reusing discovery.

One live, summary-only request against the 14 cached Alphabet search-evidence
records succeeded with 14 unique relevance assessments and five developments.
It used no discovery or article retrieval and did not persist a new briefing.
This validates the corrected schema with that source cardinality, not a replay
of the original failed model response or independent verification of its facts.

After this fix, all 147 Python tests and the JavaScript regression checks passed.
No graphical browser verification was performed; the UI and public response
shape are unchanged. The existing TestClient deprecation warning remains.

## Briefing progress animation

The JavaScript progress tests hold the summary request open to check that the
indicator stays active through searching/retrieval/summarization, stops on success
or HTTP/network failure, clears polling, and restores retry controls after failure.
They also verify that a late poll cannot replace the final error message.

All 147 Python tests and both JavaScript test files passed. A headless Chrome
check of rendered local fixture HTML verified hidden idle/completion states,
animated staggered opacity, placement next to the message at 390px, and steady
dots when prefers-reduced-motion is enabled. The dots are decorative and hidden
from assistive technology; the text retains role=status. No live article or
OpenAI requests were made. Existing TestClient deprecation warning remains.
