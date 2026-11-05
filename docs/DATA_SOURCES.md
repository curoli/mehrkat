# Data sources and rights

## Listings

Optional upstream: [Adanos Free Global Ticker Database](https://github.com/adanos-software/free-ticker-database).
Use venue-level data/listings.csv, not company-deduplicated tickers.csv.
Run from the project root:

```sh
python scripts/import_listings.py
```

Restart the app afterward. Downloads and retrieval timestamp/provenance stay in
ignored data/. The script follows upstream main, not a pinned release; inspect
provenance.json to see retrieval time and URL. Download failure leaves the
existing file intact. Missing/invalid data falls back to labelled sample mode.
No full snapshot is bundled. Imported stock fields: listing_key, ticker,
exchange, name, country, stock_sector, aliases, isin. Only Stock rows are used;
ETF categories are intentionally excluded. Aliases accept JSON arrays or
pipe-delimited strings; unexpected formats should be checked before use.

Read upstream [source licensing policy](https://github.com/adanos-software/free-ticker-database/blob/main/docs/SOURCE_LICENSING.md)
and source-specific terms before importing or redistributing. MIT covers their
software, not every source's exchange/reference data. Local download is not a
claim that commercial reuse or redistribution is permitted.

The four sample listings are independently curated illustrative reference facts,
not an extract of the global database. Names/tickers are attributable to
[Apple investor relations](https://investor.apple.com/),
[Microsoft investor relations](https://www.microsoft.com/en-us/Investor/), and
[SAP stock information](https://www.sap.com/integrated-reports/2025/en/stock.html).
These examples are not a maintained financial reference service. Sample aliases
are ordinary company names; the ADR listing does not reuse the ordinary-share
ISIN. Sample curation date: 2026-11-05.

## News

OpenAI web search supplies consulted sources and model-written cited claims.
Not every consulted URL is a usable news article. The app attempts to fetch
and extract public HTML at source URLs, checking robots rules at each redirect.
A missing robots file (404) permits an attempt; errors, disallow rules, or explicit
pacing requirements cause fallback. Explicit non-free-access metadata and common
subscription/consent gates also cause fallback. No restrictions are bypassed, and
we do not assert complete article coverage. Only actual extracted text or
citation-associated search findings can support a development; metadata-only
sources remain visible in debug. Dates remain unknown/unverified. Search's requested interval is
guidance, not a guaranteed hard filter. News may be incomplete or outdated.

SQLite retains generated search evidence, extracted article text and attribution
locally with configurable expiry (one day for article text by default). Expired
entries are inaccessible and pruned on subsequent writes. Publisher rights still
apply; robots permission is not a license or confirmation that publisher terms
permit every use. Review relevant source terms before using or redistributing
content. Retrieval is limited to public pages without authentication. Do not redistribute full copyrighted texts or interpret the
code's MIT license as licensing third-party news. Cache can be deleted while the
app is stopped by removing .cache/mehrkat.sqlite.

The importer was verified on 2026-11-05 against the upstream main CSV and loaded
74,800 stock rows locally. This is a retrieval observation, not a coverage or
licensing guarantee; the generated provenance file is kept with that download.

Extraction uses [Trafilatura](https://trafilatura.readthedocs.io/en/latest/corefunctions.html).
Text, including cached text, may still be incomplete or erroneous. Long articles
are explicitly truncated; PDFs, JavaScript-rendered pages, unsupported compression,
and blocked/unavailable URLs fall back to search evidence. Raw HTML is discarded.

The explicit View text used action displays cached evidence locally with publisher
links and coverage labels. Per-briefing snapshots preserve the exact input, including
truncation and fallback context, for at most 24 hours (or the shorter configured
article TTL). They contain no raw publisher HTML. This inspection feature does not
grant redistribution rights or imply complete article coverage.
