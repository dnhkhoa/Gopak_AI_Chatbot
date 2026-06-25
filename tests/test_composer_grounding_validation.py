from src.llm.grounded_composer import AnswerBrief, ComposerOutput, GroundedInsight, NumericFact, validate_composer_output


def _brief() -> AnswerBrief:
    return AnswerBrief(
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


def test_grounding_validator_rejects_unsupported_numbers():
    output = ComposerOutput(
        summary="Ket qua tong hop cho thay downtime la 999 gio.",
        insights=[GroundedInsight(finding="Downtime la 999 gio.", evidence_fact_ids=["total"], management_meaning="Can theo doi chi so nay.")],
        limitations=[],
    )

    validation = validate_composer_output(output, _brief())

    assert validation.passed is False
    assert "COMPOSER_GROUNDING_FAILED" in validation.failure_classification


def test_invalid_narrative_is_not_allowed_to_persist():
    output = ComposerOutput(
        summary="D",
        insights=[],
        limitations=[],
    )

    validation = validate_composer_output(output, _brief())

    assert validation.passed is False
    assert "COMPOSER_QUALITY_FAILED" in validation.failure_classification
