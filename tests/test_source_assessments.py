from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mehrkat.listings import SAMPLE
from mehrkat.models import RelevanceDecision
from mehrkat.summarization import briefing_schema, summarize, validate_sources


def assessment_payload(briefing):
    payload = briefing.model_dump()
    payload["relevance"] = {
        item.article_id: {"category": item.category, "reason": item.reason}
        for item in briefing.relevance
    }
    return payload


@pytest.mark.parametrize("count", [0, 14, 20, 40])
def test_every_source_is_required_in_provider_schema(evidence, briefing, count):
    first = evidence.articles[0]
    evidence.articles = [first.model_copy(update={"id": f"s_{i:016x}"}) for i in range(count)]
    schema = briefing_schema(evidence).model_json_schema()
    assessments = schema["$defs"]["SourceAssessments"]
    assert assessments.get("required", []) == [a.id for a in evidence.articles]
    assert set(assessments["properties"]) == {a.id for a in evidence.articles}
    assert assessments["additionalProperties"] is False
    assert schema["properties"]["relevance"]["$ref"].endswith("/SourceAssessments")


def test_schema_rejects_missing_and_invented_assessments(evidence, briefing):
    output_type = briefing_schema(evidence)
    payload = assessment_payload(briefing)
    del payload["relevance"][evidence.articles[1].id]
    with pytest.raises(ValidationError):
        output_type.model_validate(payload)
    payload = assessment_payload(briefing)
    payload["relevance"]["invented-source"] = {"category": "direct", "reason": "Test"}
    with pytest.raises(ValidationError):
        output_type.model_validate(payload)


@pytest.mark.parametrize("count", [14, 20, 40])
def test_large_evidence_round_trips_to_public_decision_list(evidence, briefing, count):
    # Mirrors Alphabet's 14-source cardinality without copying publisher text.
    first = evidence.articles[0]
    evidence.articles = [
        first.model_copy(update={"id": f"s_{i:016x}", "content_status": "search_evidence" if i == 0 else "metadata_only",
                                 "evidence_text": first.evidence_text if i == 0 else ""})
        for i in range(count)
    ]
    briefing.developments[0].source_ids = [evidence.articles[0].id]
    briefing.relevance = [
        RelevanceDecision(article_id=a.id, category="direct" if i == 0 else "uncertain", reason="Fixture only")
        for i, a in enumerate(evidence.articles)
    ]
    client = Mock()
    def parse(**kwargs):
        return SimpleNamespace(status="completed", output_parsed=kwargs["text_format"].model_validate(assessment_payload(briefing)))
    client.responses.parse.side_effect = parse
    result = summarize(client, "test-model", SAMPLE[0], evidence)
    assert len(result.relevance) == count
    assert [decision.article_id for decision in result.relevance] == [article.id for article in evidence.articles]
    assert validate_sources(result, evidence) is result
    client.responses.parse.assert_called_once()
    client.responses.create.assert_not_called()
    request = client.responses.parse.call_args.kwargs
    assert request["max_output_tokens"] == 5000 + 120 * count
    assert "tools" not in request


def test_duplicate_input_source_ids_fail_before_api_call(evidence):
    evidence.articles.append(evidence.articles[0].model_copy())
    client = Mock()
    with pytest.raises(ValueError, match="duplicate source IDs"):
        summarize(client, "test-model", SAMPLE[0], evidence)
    client.responses.parse.assert_not_called()


def test_duplicate_public_decisions_still_fail_validation(evidence, briefing):
    briefing.relevance.append(briefing.relevance[0].model_copy())
    with pytest.raises(ValueError, match="each source"):
        validate_sources(briefing, evidence)


def test_conversion_keeps_unknown_citations_rejected(evidence, briefing, client):
    briefing.developments[0].source_ids = ["invented"]
    with pytest.raises(ValueError, match="unknown"):
        summarize(client, "test-model", SAMPLE[0], evidence)


def test_official_sdk_serializes_and_parses_required_source_keys(evidence, briefing):
    import json
    import httpx
    from openai import OpenAI

    def respond(request):
        body = json.loads(request.content)
        output_format = body["text"]["format"]
        assert output_format["strict"] is True
        assessments = output_format["schema"]["$defs"]["SourceAssessments"]
        assert assessments["required"] == [article.id for article in evidence.articles]
        assert assessments["additionalProperties"] is False
        return httpx.Response(200, json={
            "id": "resp_fixture", "object": "response", "created_at": 1,
            "model": "test-model", "status": "completed",
            "output": [{
                "id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(assessment_payload(briefing)), "annotations": []}],
            }],
        })

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = OpenAI(api_key="fixture-key", http_client=transport, max_retries=0)
        result = summarize(client, "test-model", SAMPLE[0], evidence)
    assert result.model_dump() == briefing.model_dump()
