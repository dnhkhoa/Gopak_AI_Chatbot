from src.application.grounding import (
    AllowedNumericFact,
    GroundedComposerValidator,
    deterministic_table_commentary,
)
from src.application.schemas import ChatResponse, TablePayload


def test_grounded_validator_rejects_unsupported_numbers_and_conversions():
    validator = GroundedComposerValidator(
        [
            AllowedNumericFact("duration", 413.57, "413,57 giờ"),
            AllowedNumericFact("count", 1469, "1.469"),
        ]
    )

    assert validator.validate("Máy 11 có khoảng 69 lần dừng trong 27 ngày.").passed is False
    assert validator.validate("Máy này gần một nửa tổng downtime.").passed is False


def test_grounded_validator_accepts_displayed_facts():
    validator = GroundedComposerValidator(
        [
            AllowedNumericFact("machine", 11, "11"),
            AllowedNumericFact("duration", 413.57, "413,57 giờ"),
            AllowedNumericFact("count", 1469, "1.469"),
            AllowedNumericFact("avg", 16, "16 phút 54 giây"),
        ]
    )

    result = validator.validate("Máy 11 đứng đầu với 413,57 giờ, gồm 1.469 lần ghi nhận và trung bình 16 phút 54 giây.")

    assert result.passed


def test_deterministic_table_commentary_uses_only_table_values():
    response = ChatResponse(
        message_id="m1",
        conversation_id="c1",
        response_type="table",
        table=TablePayload(
            columns=["Máy", "Tổng thời gian downtime", "Số lần ghi nhận"],
            rows=[
                {"Máy": "Máy 11", "Tổng thời gian downtime": "413,57 giờ", "Số lần ghi nhận": "1.469"},
                {"Máy": "Máy 12", "Tổng thời gian downtime": "323,15 giờ", "Số lần ghi nhận": "1.654"},
            ],
        ),
    )

    text = deterministic_table_commentary("nhận xét top 5 máy", response)

    assert "413,57 giờ" in text
    assert "69 lần" not in text
    assert "ngày" not in text
