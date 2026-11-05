"""Opt-in, bounded summary evaluation on synthetic evidence; never run live in CI."""
import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import summarization
from .cache import content_key
from .config import ROOT, Settings
from .models import Discovery, Evidence, Listing

FIXTURES = ROOT / "evals/stock_briefings.json"
DIMENSIONS = ("factual_support", "relevance", "event_grouping", "uncertainty", "instruction_safety", "usefulness")


@dataclass
class EvaluationCase:
    id: str
    description: str
    listing: Listing
    discovery: Discovery
    review_checks: list[str]
    expected_insufficient_news: bool | None
    excluded_source_ids: list[str]


def load_cases(path=FIXTURES):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    listing = Listing.model_validate(data["listing"])
    cases = []
    for case in data["cases"]:
        discovery = Discovery(
            listing_key=listing.listing_key, window_start=data["window_start"],
            window_end=data["window_end"], discovered_at=data["window_end"],
            articles=[Evidence(retrieved_at=data["window_end"], **article) for article in case["articles"]],
            limitations=["Synthetic evaluation evidence; not actual news.", "Publication dates are unverified."],
        )
        ids = [article.id for article in discovery.articles]
        if len(ids) != len(set(ids)) or not set(case["excluded_source_ids"]) <= set(ids):
            raise ValueError("Invalid evaluation source IDs.")
        cases.append(EvaluationCase(
            id=case["id"], description=case["description"], listing=listing,
            discovery=discovery, review_checks=case["review_checks"],
            expected_insufficient_news=case["expected_insufficient_news"],
            excluded_source_ids=case["excluded_source_ids"],
        ))
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Evaluation case IDs must be unique.")
    return data["version"], cases


def evaluate_case(client, model, case):
    result = {
        "case_id": case.id, "description": case.description,
        "evidence_hash": content_key(case.discovery.model_dump(mode="json")),
        "review_checks": case.review_checks,
        "human_review": {dimension: None for dimension in DIMENSIONS},
        "review_decision": "not_reviewed", "review_notes": None,
    }
    try:
        briefing = summarization.summarize(client, model, case.listing, case.discovery)
        cited = {source_id for event in briefing.developments for source_id in event.source_ids}
        checks = {"schema_and_source_validation": True,
                  "excluded_sources_not_cited": not cited.intersection(case.excluded_source_ids)}
        if case.expected_insufficient_news is not None:
            checks["expected_insufficient_news"] = briefing.insufficient_news == case.expected_insufficient_news
        result.update(briefing=briefing.model_dump(mode="json"), automatic_checks=checks,
                      automatic_pass=all(checks.values()))
    except Exception as exc:
        # Provider exceptions may contain request bodies or authorization details.
        result.update(error_type=type(exc).__name__, automatic_pass=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate and list fixtures without API calls (default).")
    mode.add_argument("--live", action="store_true", help="Make one billable summary call per selected case; no retries.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Case ID; repeat to select at most two in live mode.")
    parser.add_argument("--output", type=Path, help="New .json report path; default: ignored .cache/ai-evaluation/.")
    args = parser.parse_args(argv)
    version, cases = load_cases()
    chosen = set(args.case_ids or [])
    if chosen - {case.id for case in cases}:
        parser.error("Unknown case ID. Run --dry-run to list available cases.")
    selected = [case for case in cases if not chosen or case.id in chosen]
    if not args.live:
        if args.output:
            parser.error("--output requires --live; dry runs do not write reports.")
        for case in selected:
            print(f"{case.id}: {len(case.discovery.articles)} synthetic sources — {case.description}")
        print("Dry run complete; no API key loaded and no network requests made.")
        return 0
    if not chosen or len(chosen) > 2:
        parser.error("Live evaluation requires one or two explicit --case selections.")
    settings = Settings.from_env()
    if not settings.api_key:
        parser.error("Set OPENAI_API_KEY in the environment or project .env before using --live.")
    timestamp = datetime.now(timezone.utc)
    output = args.output or ROOT / ".cache/ai-evaluation" / (timestamp.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    if output.suffix.lower() != ".json":
        parser.error("The report must use a .json filename.")
    if output.exists():
        parser.error("Report already exists. Choose a new path; reports are never overwritten.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the path before making paid calls, to avoid paying then discovering
    # that a report cannot be written. Keep even unsuccessful runs for comparison.
    from openai import OpenAI
    with output.open("x", encoding="utf-8") as report_file, OpenAI(
        api_key=settings.api_key, timeout=60, max_retries=0,
    ) as client:
        results = [evaluate_case(client, settings.summary_model, case) for case in selected]
        report = {
            "synthetic_evidence_only": True, "dataset_version": version,
            "generated_at": timestamp.isoformat(), "model": settings.summary_model,
            "summary_version": summarization.VERSION, "cases": results,
        }
        json.dump(report, report_file, ensure_ascii=False, indent=2)
        report_file.write("\n")
    for result in results:
        print(f"{result['case_id']}: automatic checks {'passed' if result['automatic_pass'] else 'failed'}; human review required")
    print(f"Report: {output}")
    return 0 if all(result["automatic_pass"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
