# Testing strategy

We test the risks most likely to undermine a cited news briefing: choosing the
wrong listing, using unsupported evidence, mishandling failed retrieval, losing
source provenance, spending on unintended API calls, and presenting misleading
model output. Test count is not our quality target.

## Run the deterministic suites

From the repository root, after installing the dev extra:

```sh
pytest -q
node --test tests/js/*.test.cjs
```

Python tests use temporary settings/SQLite databases, synthetic evidence and
mocked OpenAI/publisher responses. Outbound IPv4/IPv6 connections are blocked;
local Unix socket pairs remain available for TestClient. JavaScript tests use
Node.js 20+ and DOM/fetch stubs; no npm install is needed. Neither suite requires
an API key, a data download, a browser, or paid calls.

## Layers and responsibilities

| Layer | Main risks and coverage | When |
| --- | --- | --- |
| Unit | Listing identity/filter semantics; URL deduplication; robots/redirect/IP restrictions; extraction/fallback; cache expiry/keys; source-ID validation and coverage counts | Every change |
| API/integration | Search → exact listing → mocked briefing → cited source → exact cached evidence; missing key/provider errors; no paid calls during browsing; cache reuse; snapshots survive restarts | Every change |
| JavaScript | Filter restoration/counts/resets; query-preserving navigation; progress lifecycle and late-response races | Every change |
| Browser smoke | Real rendering, keyboard/focus behavior, popups, animation/reduced motion, narrow-screen layout | UI changes and before submission |
| AI evaluation | Factual support, relevance, event grouping, uncertainty and resistance to article instructions | Prompt/model changes and before submission |

The official OpenAI SDK is exercised through MockTransport as well as SDK-shaped
fixtures. Extraction includes real parser runs on invented local HTML. Tests
assert observable behavior and important invariants rather than exact summary
wording or every implementation detail.

## CI

[Tests workflow](../.github/workflows/tests.yml) runs on pushes and pull requests:
Python 3.11 and 3.13 install the dev extra, check dependencies, run pytest and
validate the AI corpus in dry-run mode. Node.js 22 runs JavaScript syntax and
regression checks. Jobs have read-only repository access and no OpenAI secret.
Dependency installation needs internet; test/evaluation dry-run execution does
not. Live smoke checks and paid AI evaluations are deliberately excluded.

A failed automated job blocks our submission checklist. Reproduce its command
locally, fix the behavior and add a focused regression for a meaningful bug.
Branch protection is not configured by this workflow.

## Model quality: a separate decision

Passing mocked tests establishes code behavior, not truthful or useful model
output. [AI_EVALUATION.md](AI_EVALUATION.md) defines a small fixed synthetic corpus,
an explicit billable runner and a human pass/fail rubric. Run it when prompts,
models or evidence handling change. Never treat schema validation, a provider
success response or an automatic fixture check as a factual-quality approval.

## Browser and live smoke checklist

1. Start from a fresh local setup; root renders search without a key.
2. Search SAP, select an exchange explicitly, use several filters, reset one,
   and confirm selections/counts survive listing and briefing navigation.
3. Generate a briefing; verify progress messages/animation, failure recovery and
   reduced-motion behavior. Inspect popups with keyboard, Escape and Close.
4. Follow source links and inspect cached text; confirm coverage labels and exact
   excerpts/fallbacks. Old snapshot links must not show a newer briefing's text.
5. Repeat within TTL; confirm cache reuse. Check the layout on a narrow screen.
6. Review factual claims against the supplied evidence and original source pages.

An explicit bounded provider check is available:

```sh
python scripts/smoke.py
```

It may incur cost: at most one discovery request plus one summary request, with
retries disabled, or fewer on cache hits/failure. Publisher retrieval may also
occur. It uses the runtime key without printing it. Success verifies connectivity
and parsing for that run, not exhaustive discovery or factual correctness.

## Submission gate and limits

- All deterministic CI jobs pass.
- The main browser workflow has been checked after UI changes.
- One bounded live provider check succeeds, or the exact access/quota limitation
  is recorded.
- Changed AI behavior is reviewed against the fixed corpus; critical unsupported
  claims, invalid attribution, or instruction following fail review.
- Record model/prompt versions and known limitations; never imply checks ran
  when they did not.

Current gaps: no committed browser automation suite, no statistically reliable
model benchmark, no production load test, and no independent guarantee of article
completeness or publication dates. The existing Starlette/httpx TestClient
deprecation warning is visible; a dependency migration can address it separately.
