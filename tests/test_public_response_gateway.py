from __future__ import annotations

from src.application.public_response import PublicResponseSanitizer, scan_response
from src.application.schemas import ChatResponse, SourcePayload, TablePayload


def _response(**overrides):
    payload = {
        "message_id": "m1",
        "conversation_id": "c1",
        "response_type": "table",
        "title": "APQOEE Cumulative",
        "summary": "Cumulative OEE: 57.55 % (cumulative through 2025-11-10T23:00:00+07:00)",
        "table": TablePayload(
            columns=["source_id", "source", "metric", "value", "unit", "time_scope", "snapshot_time"],
            rows=[
                {
                    "source_id": "apqoee_cumulative",
                    "source": "APQOEE Cumulative",
                    "metric": "Cumulative OEE",
                    "value": 57.55,
                    "unit": "%",
                    "time_scope": "cumulative through 2025-11-10T23:00:00+07:00",
                    "snapshot_time": "2025-11-10T23:00:00+07:00",
                },
                {
                    "source_id": "apqoee_cumulative",
                    "source": "APQOEE Cumulative",
                    "metric": "Cumulative Availability",
                    "value": 61.24,
                    "unit": "%",
                    "time_scope": "cumulative through 2025-11-10T23:00:00+07:00",
                    "snapshot_time": "2025-11-10T23:00:00+07:00",
                },
            ],
        ),
        "sources": [SourcePayload(name="APQOEE Cumulative")],
        "metadata": {"status": "COMPLETED"},
    }
    payload.update(overrides)
    return ChatResponse(**payload)


def test_apqoee_public_response_is_vietnamese_and_compact():
    response = PublicResponseSanitizer().sanitize(_response())

    assert response.title == "APQOEE tích lũy"
    assert response.table is not None
    assert response.table.columns == ["Chỉ số", "Giá trị"]
    assert response.table.rows[0] == {"Chỉ số": "OEE tích lũy", "Giá trị": "57,55%"}
    assert "Kết quả tính đến 23:00 ngày 10/11/2025" in response.summary
    assert "- OEE tích lũy: 57,55%" in response.summary
    assert "APQOEE Cumulative" not in response.summary
    assert "2025-11-10T23:00:00+07:00" not in response.summary
    assert "source_id" not in str(response.model_dump())
    assert scan_response(response)["clean"]


def test_error_response_uses_business_vietnamese_message():
    response = ChatResponse(
        message_id="m2",
        conversation_id="c1",
        response_type="refusal",
        title="Calculation is not enabled",
        summary="Period-specific APQOEE/OEE is locked until PERFORMANCE_FORMULA_MODE is configured with an approved Performance formula.",
        metadata={"status": "PLAN_REJECTED"},
    )
    response = PublicResponseSanitizer().sanitize(response)

    assert response.title == "Chưa thể thực hiện phép tính này"
    assert "Chưa thể tính OEE riêng theo ngày" in response.summary
    assert "Performance formula" not in response.summary
    assert "Period-specific" not in response.summary
    assert scan_response(response)["clean"]


def test_clarification_response_is_localized():
    response = ChatResponse(
        message_id="m3",
        conversation_id="c1",
        response_type="clarification",
        title="Clarification required",
        summary="Please specify whether you want OEE, machine downtime, loss assignment, or a comparison across those sources.",
        metadata={"status": "CLARIFICATION_REQUIRED"},
    )
    response = PublicResponseSanitizer().sanitize(response)

    assert "Bạn muốn xem OEE" in response.summary
    assert "Please specify" not in response.summary
    assert scan_response(response)["clean"]
