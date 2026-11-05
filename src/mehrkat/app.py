from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import APIConnectionError, APIStatusError, APITimeoutError

from .config import Settings
from .listings import Directory, normalize
from .models import Listing, SummaryResult
from .service import NewsService

HERE = Path(__file__).parent


def create_app(settings=None, client=None):
    settings = settings or Settings.from_env()
    directory = Directory(settings.listings_path)
    service = NewsService(settings, client)
    app = FastAPI(title="mehrkat")
    app.state.service = service
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def page(request, name, **context):
        search_params = [(key, value) for key, value in request.query_params.multi_items()
                         if key in {"q", "exchange", "country", "sector"} and value]
        selected_filters = {}
        for field, options in directory.filter_options.items():
            requested = {normalize(value) for value in request.query_params.getlist(field)}
            # Restore canonical checkbox values using the same matching rules
            # as directory filtering, including case and whitespace tolerance.
            selected_filters[field] = [value for value in options if normalize(value) in requested]
        return templates.TemplateResponse(request=request, name=name, context={
            "directory_status": directory.status, "lookback": settings.lookback_hours,
            "filter_options": directory.filter_options, "selected_filters": selected_filters,
            "search_url": "/?" + urlencode(search_params) if search_params else "/",
            "search_suffix": "?" + urlencode(search_params) if search_params else "", **context,
        })

    def lookup(key):
        listing = directory.by_key.get(key)
        if listing is None:
            raise HTTPException(404, "Listing not found. Search and select an exact listing.")
        return listing

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return page(request, "index.html")

    @app.get("/api/listings", response_model=list[Listing])
    def search(q: Annotated[str, Query(max_length=200)] = "",
               exchange: Annotated[list[str] | None, Query()] = None,
               country: Annotated[list[str] | None, Query()] = None,
               sector: Annotated[list[str] | None, Query()] = None):
        return directory.search(q, exchange, country, sector)

    @app.get("/listing", response_class=HTMLResponse)
    def listing(request: Request, key: str):
        return page(request, "listing.html", listing=lookup(key))

    @app.post("/api/summary", response_model=SummaryResult,
              response_model_exclude={"discovery": {"articles": {"__all__": {"evidence_text", "search_evidence_text"}}}})
    def summary(key: str, hours: Annotated[int | None, Query(ge=1, le=168)] = None):
        listing = lookup(key)
        try:
            return service.run(listing, hours or settings.lookback_hours)
        except APITimeoutError:
            raise HTTPException(504, "OpenAI timed out. Please retry; completed discovery is cached.") from None
        except APIConnectionError:
            raise HTTPException(502, "Cannot reach OpenAI. Check your network and retry.") from None
        except APIStatusError as exc:
            # Never relay provider messages, request bodies, headers, or credentials.
            messages = {
                401: "OpenAI rejected the API key. Check OPENAI_API_KEY and restart.",
                403: "OpenAI denied access. Check account permissions and configured models.",
                404: "Configured OpenAI model unavailable. Check OPENAI_DISCOVERY_MODEL and OPENAI_SUMMARY_MODEL.",
                429: "OpenAI quota or rate limit reached. Check billing or retry later.",
            }
            raise HTTPException(502, messages.get(exc.status_code, "OpenAI request failed. Retry later or check model configuration.")) from None
        except ValueError as exc:
            # Only fixed application validation messages may reach the browser.
            if type(exc) is ValueError:
                raise HTTPException(422, str(exc)) from None
            raise HTTPException(502, "The provider response could not be validated.") from None
        except RuntimeError:
            raise HTTPException(409, "Another briefing is running. Please wait and retry.") from None

    @app.get("/result", response_class=HTMLResponse)
    def result(request: Request, briefing: str | None = None):
        selected = service.get_result(briefing) if briefing is not None else service.last_result
        if selected is None:
            raise HTTPException(404, "Briefing unavailable or expired. Generate a new briefing from Search.")
        return page(request, "result.html", result=selected,
                    sources={a.id: a for a in selected.discovery.articles})

    @app.get("/sources/{result_id}/{source_id}", response_class=HTMLResponse)
    def source_text(request: Request, result_id: str, source_id: str):
        selected = service.get_result(result_id)
        if selected is None:
            raise HTTPException(404, "Cached briefing unavailable or expired. Generate a new briefing from Search.")
        source = next((article for article in selected.used_sources if article.id == source_id), None)
        if source is None:
            raise HTTPException(404, "Source was not cited in this briefing.")
        response = page(request, "source.html", result=selected, source=source)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/status")
    def status():
        return {"phase": service.phase}

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return page(request, "info.html", title="Settings", values={
            "API key configured": bool(settings.api_key),
            "Discovery model": settings.discovery_model, "Summary model": settings.summary_model,
            "Default lookback (hours)": settings.lookback_hours,
            "Discovery TTL (seconds)": settings.discovery_ttl,
            "Article text TTL (seconds)": settings.article_ttl,
            "Directory": directory.status,
        }, note="Configure OPENAI_API_KEY, OPENAI_DISCOVERY_MODEL, OPENAI_SUMMARY_MODEL, NEWS_LOOKBACK_HOURS, DISCOVERY_CACHE_TTL_SECONDS, ARTICLE_CACHE_TTL_SECONDS, LISTINGS_PATH and CACHE_PATH in the environment or .env, then restart.")

    @app.get("/monitoring", response_class=HTMLResponse)
    def monitoring(request: Request):
        return page(request, "info.html", title="Monitoring", values=service.metrics,
                    note="Process-local counters; reset on restart. Cache entries persist in SQLite.")

    @app.get("/debug", response_class=HTMLResponse)
    def debug(request: Request):
        last = service.last_result
        values = {"Selected listing": last.listing.listing_key if last else "None"}
        if last:
            values["Model caveats"] = " | ".join(last.briefing.limitations) or "None"
            for article in last.discovery.articles:
                decision = next((r for r in last.briefing.relevance if r.article_id == article.id), None)
                values[article.id] = f"{article.url} | {article.content_status} | publication date unverified | {decision.category if decision else 'not assessed'}: {decision.reason if decision else ''} | {article.retrieval_note or 'not attempted'}"
        return page(request, "info.html", title="Debug", values=values,
                    note="Latest process-local result only. No full article texts or credentials are shown.")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
