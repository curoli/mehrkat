# mehrkat

AI-powered stock news summaries. Find a company or ticker, select a listing,
then generate a cited news briefing.

## Run locally

1. Set your OpenAI API key in the project-root `.env` (or export it):

   ```dotenv
   OPENAI_API_KEY=your-key-here
   ```

2. Install dependencies (Python 3.11+):

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Start mehrkat:

   ```sh
   uvicorn mehrkat.app:app --reload
   ```

4. Open http://127.0.0.1:8000/

Starts offline with a labelled sample directory: Apple, Microsoft, and SAP
on two exchanges. Only generating a briefing needs network access and your
OpenAI key. Optional larger local directory: `python scripts/import_listings.py`;
review [data terms](docs/DATA_SOURCES.md) first.

## Test

```sh
pytest -q
```

## More information

[Architecture](docs/ARCHITECTURE.md) · [Data sources](docs/DATA_SOURCES.md) ·
[Testing](docs/TESTING.md) · [Design decisions](docs/DESIGN_DECISIONS.md) ·
[Limitations](docs/LIMITATIONS.md) · [AI assistance](docs/AI_ASSISTANCE.md)

Code is [MIT licensed](LICENSE); third-party data and news retain their own terms.
