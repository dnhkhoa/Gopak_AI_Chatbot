import pytest
from pydantic import ValidationError

from src.llm.semantic_contracts import SemanticIntent, SemanticResolution, TurnRelationship


def test_semantic_resolution_forbids_extra_fields():
    with pytest.raises(ValidationError):
        SemanticResolution.model_validate(
            {
                "intent": "AGGREGATION",
                "turn_relationship": "NEW_REQUEST",
                "metrics": ["total_downtime"],
                "sql": "select * from data",
            }
        )


def test_semantic_resolution_uses_centralized_enums():
    resolution = SemanticResolution(
        intent=SemanticIntent.TIME_TREND,
        turn_relationship=TurnRelationship.NEW_REQUEST,
        dimensions=["date"],
        metrics=["total_downtime"],
        time_grain="day",
        confidence=0.8,
    )

    assert resolution.intent is SemanticIntent.TIME_TREND
    assert resolution.turn_relationship is TurnRelationship.NEW_REQUEST
    assert resolution.model_dump(mode="json")["intent"] == "TIME_TREND"
