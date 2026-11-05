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
`python scripts/smoke.py`. It performs at most one request per stage with retries
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
download/compression limits, and omission of article bodies from browser/API/debug
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
node --test tests/js/search.test.cjs
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
