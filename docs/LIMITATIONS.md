# Limitations

- Web search is not exhaustive, and may find older articles. Publication dates are
  not independently verified; the UI marks all as unknown/unverified.
- Retrieval attempts public article HTML but extraction completeness is unverified.
  Articles may be partial, stale, or truncated. Failed/restricted retrieval falls
  back to generated cited search claims. Models may omit, misread, or hallucinate
  facts despite source-ID validation.
- Robots checks and simple restriction detection are conservative heuristics, not
  a guarantee of publisher permission or accurate paywall detection. No login,
  consent bypass, browser automation or restricted-content extraction is attempted.
- Extracted text is capped at 30,000 characters per source and 120,000 characters
  per briefing. Longer content is labelled as an excerpt; when the briefing budget
  is exhausted the source uses search findings instead. Cached text expires after
  a day by default, so publisher corrections can take that long to appear.
- HTML downloads are capped at 2 MB with an eight-second network deadline per
  source and at most four concurrent retrievals. DNS uses the OS resolver timeout.
  Many sources can extend total generation time. PDFs and JavaScript-only pages
  are unsupported; sites without checkable robots policy fall back.
- Relevance, event grouping and investor implications are qualitative model work.
  Prompts and mocked tests cannot establish real-world factual accuracy.
- Briefings target 350–600 words only when evidence supports that length. Scarce
  evidence should produce an honest shorter or insufficient-news result.
- The sample covers only four listings. Imported directories can be incomplete,
  stale, or subject to restrictions; unsupported formats fall back to the sample.
- Local single-user operation only. Latest result and status are process-wide;
  another tab can replace the result. Do not expose this server publicly without
  authentication, per-user state, CSRF/rate controls, and a security review.
- One workflow runs at a time. SDK timeout is 60 seconds per request with one
  transient retry; two stages may take several minutes. A browser disconnect
  does not cancel an in-flight SDK request.
- No portfolio management, price predictions, investment recommendations,
  background ingestion, or unrestricted full-site crawling.
