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
