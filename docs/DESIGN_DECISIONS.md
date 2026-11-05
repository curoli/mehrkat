# Design decisions

- Python/FastAPI, Pydantic, Jinja2 and vanilla JavaScript keep the code easy to
  explain and modify during live pair programming. No frontend build or CDN.
- Official OpenAI SDK uses Responses web search only for discovery; structured
  summarization assesses relevance and groups developments in one separate call.
  Discovery uses native source metadata and inline citation annotations instead
  of asking a model to invent a JSON list of articles.
- SQLite needs no service setup and lets discovery survive a failed summary.
  Prompts and schemas are versioned explicitly.
- Exact listing keys preserve venue identity; company metadata supplies news
  context without excluding international sector events.
- Public article text is attempted after discovery with Trafilatura. A URL cache
  allows reuse across discovery refreshes and listings; failures preserve cited
  search findings. Extraction is labelled as completeness unverified, and long
  text is labelled as an excerpt. We do not interpret successful HTML download
  as proof of complete article access.
- Publication dates remain null/unverified because this version has no independent
  publication-date extractor. Model claims about dates are not metadata verification.
- No force-refresh control: TTL gives a predictable default cost boundary.
- A demonstrative directory keeps startup independent of downloads or credentials.
  Full data imports remain optional and ignored by Git.
- Configurable gpt-4.1 defaults favor a simple non-reasoning interface. Account
  availability varies; change model environment variables if unavailable.
  Check current model lifecycle before relying on this default long term.

Implementation references:
[Web search](https://developers.openai.com/api/docs/guides/tools-web-search),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1).
Structured Outputs validates shape, not truth.
