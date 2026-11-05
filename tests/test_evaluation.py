import json
from unittest.mock import MagicMock, Mock

import pytest

from mehrkat import evaluation
from mehrkat.config import Settings
from mehrkat.models import StockBriefing


def synthetic_summary(client, model, listing, discovery):
    return StockBriefing(
        overview="Synthetic fixture briefing." if discovery.articles else "Insufficient news.",
        developments=[{"title": "Fixture development", "factual_summary": "Fixture only",
                       "possible_implications": None, "source_ids": [discovery.articles[0].id]}] if discovery.articles else [],
        relevance=[{"article_id": a.id, "category": "direct", "reason": "Fixture"} for a in discovery.articles],
        insufficient_news=not discovery.articles, limitations=["Synthetic evaluation only"],
    )


def test_corpus_is_fixed_synthetic_and_valid():
    version, cases = evaluation.load_cases()
    assert version == 1
    assert {case.id for case in cases} == {"grouping", "conflicting", "insufficient", "injection"}
    for case in cases:
        assert case.review_checks
        assert "fictional" in case.listing.name
        assert all(a.url.host == "example.com" for a in case.discovery.articles)
    assert any("UNTRUSTED WEBPAGE INSTRUCTION" in a.evidence_text
               for case in cases for a in case.discovery.articles)


def test_dry_run_never_loads_credentials_or_constructs_api_client(monkeypatch, capsys):
    settings = Mock(side_effect=AssertionError("Dry run must not load API credentials"))
    client = Mock(side_effect=AssertionError("Dry run must not construct API client"))
    monkeypatch.setattr(evaluation.Settings, "from_env", settings)
    monkeypatch.setattr("openai.OpenAI", client)
    assert evaluation.main(["--dry-run"]) == 0
    assert evaluation.main(["--case", "grouping"]) == 0
    assert "no API key loaded" in capsys.readouterr().out
    settings.assert_not_called()
    client.assert_not_called()


@pytest.mark.parametrize("args", [
    ["--live"], ["--live", "--case", "grouping", "--case", "conflicting", "--case", "injection"],
    ["--case", "unknown"], ["--dry-run", "--output", "report.json"],
])
def test_invalid_invocations_fail_before_credentials_or_paid_calls(monkeypatch, args):
    settings = Mock(side_effect=AssertionError("Invalid invocation must not load credentials"))
    monkeypatch.setattr(evaluation.Settings, "from_env", settings)
    with pytest.raises(SystemExit) as error:
        evaluation.main(args)
    assert error.value.code == 2
    settings.assert_not_called()


def test_live_evaluation_is_bounded_and_requires_human_review(monkeypatch, tmp_path):
    settings = Settings(api_key="fixture-key")
    monkeypatch.setattr(evaluation.Settings, "from_env", lambda: settings)
    constructor = MagicMock()
    fake_client = constructor.return_value.__enter__.return_value
    monkeypatch.setattr("openai.OpenAI", constructor)
    summarize = Mock(side_effect=synthetic_summary)
    monkeypatch.setattr(evaluation.summarization, "summarize", summarize)
    output = tmp_path / "report.json"
    assert evaluation.main(["--live", "--case", "grouping", "--case", "insufficient", "--output", str(output)]) == 0
    constructor.assert_called_once_with(api_key="fixture-key", timeout=60, max_retries=0)
    assert summarize.call_count == 2
    assert all(call.args[0] is fake_client for call in summarize.call_args_list)
    report = json.loads(output.read_text())
    assert report["synthetic_evidence_only"] and report["dataset_version"] == 1
    assert report["summary_version"] == evaluation.summarization.VERSION
    assert len(report["cases"]) == 2
    for case in report["cases"]:
        assert case["automatic_pass"]
        assert case["review_decision"] == "not_reviewed"
        assert all(value is None for value in case["human_review"].values())
        assert len(case["evidence_hash"]) == 64
    assert "fixture-key" not in output.read_text()
    # A rerun must not overwrite earlier evidence or incur another call.
    with pytest.raises(SystemExit):
        evaluation.main(["--live", "--case", "grouping", "--output", str(output)])
    assert summarize.call_count == 2


def test_case_expectations_are_separate_from_schema_validation(monkeypatch):
    _, cases = evaluation.load_cases()
    grouping = next(case for case in cases if case.id == "grouping")
    wrong = synthetic_summary(None, None, grouping.listing, grouping.discovery)
    wrong.developments[0].source_ids = ["unrelated_cafe"]
    monkeypatch.setattr(evaluation.summarization, "summarize", lambda *args: wrong)
    result = evaluation.evaluate_case(Mock(), "fixture-model", grouping)
    assert result["automatic_checks"]["schema_and_source_validation"]
    assert not result["automatic_checks"]["excluded_sources_not_cited"]
    assert not result["automatic_pass"]
    assert result["review_decision"] == "not_reviewed"


def test_provider_errors_are_sanitized_in_reports(monkeypatch):
    _, cases = evaluation.load_cases()
    monkeypatch.setattr(evaluation.summarization, "summarize",
                        Mock(side_effect=RuntimeError("private provider request payload")))
    result = evaluation.evaluate_case(Mock(), "fixture-model", cases[0])
    assert result["error_type"] == "RuntimeError"
    assert not result["automatic_pass"]
    assert "private provider request payload" not in json.dumps(result)


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
@pytest.mark.parametrize("family", ["AF_INET", "AF_INET6"])
def test_test_suite_blocks_outbound_connections_before_using_socket(method, family):
    import socket
    from types import SimpleNamespace
    # Exercise the installed guard without requiring permission to create an
    # internet socket in a restricted local sandbox.
    connection = SimpleNamespace(family=getattr(socket, family))
    with pytest.raises(AssertionError, match="real connections are disabled"):
        getattr(socket.socket, method)(connection, ("203.0.113.1", 443))
