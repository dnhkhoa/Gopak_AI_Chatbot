import json

from src.llm.semantic_resolver import parse_semantic_resolution


def test_free_text_intent_is_rejected_by_strict_validator():
    raw = json.dumps(
        {
            "schema_version": "semantic_resolution.v1",
            "intent": "User wants to analyze the selected file",
            "turn_relationship": "NEW_REQUEST",
            "metrics": ["total_downtime"],
            "confidence": 0.6,
        }
    )

    resolution, trace = parse_semantic_resolution(raw)

    assert resolution is None
    assert "ENUM_VALIDATION_FAILED" in trace.failure_classification
    assert trace.resolver_enum_valid is False
