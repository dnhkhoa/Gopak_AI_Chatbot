import json

import pytest
from pydantic import ValidationError

from src.llm.grounded_composer import AnswerBrief, ComposerOutput, GroundedComposer, NumericFact


def test_answer_brief_forbids_extra_fields():
    with pytest.raises(ValidationError):
        AnswerBrief.model_validate(
            {
                "request_summary": "Tong hop downtime",
                "response_type": "analysis",
                "numeric_facts": [],
                "comparison_facts": [],
                "allowed_claims": [],
                "sources": [],
                "limitations": [],
                "required_sections": [],
                "requested_insight_count": None,
                "raw_sql": "select 1",
            }
        )


def test_grounded_composer_uses_deterministic_recovery_when_model_unavailable():
    brief = AnswerBrief(
        request_summary="Tong hop downtime",
        response_type="analysis",
        numeric_facts=[
            NumericFact(
                fact_id="total",
                label="Total downtime",
                value=123.0,
                formatted_value="123",
                unit="gio",
                source_result_id="result-1",
            )
        ],
        allowed_claims=["Ket qua tong hop cho thay downtime la 123 gio."],
        sources=[{"result_id": "result-1"}],
        limitations=["Chi phan anh file dang chon."],
        required_sections=[],
    )

    result = GroundedComposer(None, None, "split_roles_same_model").compose(brief)

    assert result.trace.deterministic_recovery_used is True
    assert result.trace.recovery_reason == "MODEL_UNAVAILABLE"
    assert isinstance(result.output, ComposerOutput)
    assert "123" in result.output.summary


def test_composer_output_schema_rejects_extra_internal_payload():
    with pytest.raises(ValidationError):
        ComposerOutput.model_validate_json(
            json.dumps(
                {
                    "summary": "Ket qua da duoc tong hop tu so lieu hop le.",
                    "insights": [],
                    "limitations": [],
                    "query_plan": {"sql": "select 1"},
                }
            )
        )
