import json

from src.llm.semantic_contracts import SemanticIntent
from src.llm.semantic_resolver import parse_semantic_resolution


def test_canonicalization_accepts_only_static_taxonomy_aliases():
    raw = json.dumps(
        {
            "schema_version": "semantic_resolution.v1",
            "intent": "time trend",
            "turn_relationship": "new request",
            "dimensions": ["date"],
            "metrics": ["total_downtime"],
            "time_grain": "day",
            "confidence": 0.8,
        }
    )

    resolution, trace = parse_semantic_resolution(raw)

    assert resolution is not None
    assert resolution.intent is SemanticIntent.TIME_TREND
    assert trace.strict_parse_valid is False
    assert trace.canonicalized_parse_valid is True
    assert {item.classification for item in trace.canonicalization} == {"TAXONOMY_FORMAT_ONLY"}


def test_semantic_wrong_text_is_not_canonicalized_into_a_pass():
    raw = json.dumps(
        {
            "schema_version": "semantic_resolution.v1",
            "intent": "please decide whatever seems best",
            "turn_relationship": "new request",
            "confidence": 0.2,
        }
    )

    resolution, trace = parse_semantic_resolution(raw)

    assert resolution is None
    assert any(item.accepted is False for item in trace.canonicalization)
    assert "ENUM_VALIDATION_FAILED" in trace.failure_classification
