"""Explicit, billable two-stage live check; never run by pytest."""
from mehrkat.app import create_app
from mehrkat.listings import SAMPLE


def main():
    app = create_app()
    service = app.state.service
    # Keep verification to one discovery request plus one summary request,
    # even when the application's normal discovery uses multiple passes.
    service.settings.discovery_search_passes = 1
    from openai import OpenAI
    if not service.settings.api_key:
        print("Live smoke skipped: OPENAI_API_KEY is not configured.")
        return
    service.client = OpenAI(api_key=service.settings.api_key, timeout=60, max_retries=0)
    try:
        result = service.run(SAMPLE[0], 48)
        print(f"Live smoke succeeded: {len(result.discovery.articles)} sources; "
              f"{len(result.briefing.developments)} developments; "
              f"insufficient_news={result.briefing.insufficient_news}; "
              f"discovery_cached={result.discovery_cached}; summary_cached={result.summary_cached}")
    except Exception as exc:
        # Provider exceptions may contain secret-bearing request information.
        print(f"Live smoke failed ({type(exc).__name__}); no provider payload printed.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
