# Limitations

- Web search is not exhaustive, and may find older articles. Publication dates are
  not independently verified; the UI marks all as unknown/unverified.
- Citation-associated evidence is a generated search claim, not publisher full
  text. Models may omit, misread, or hallucinate facts despite source-ID validation.
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
  background ingestion, or full-text extraction.
