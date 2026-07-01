from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.application.capability import (
    ActiveFileCapabilityGate,
    build_dataset_capability_profile,
    build_request_requirements,
    unsupported_message,
)
from src.application.errors import CustomerErrorMessagePolicy, ErrorCode, classify_exception, is_infrastructure
from src.application.public_response import PublicResponseSanitizer, scan_response
from src.application.schemas import ChatResponse, TablePayload
from src.rendering.labels import display_label, find_internal_keys, find_unaccented_vietnamese


VI_ACCENT_CHARS = set(
    "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ĂÂĐÊÔƠƯ"
)


def _has_vietnamese_accents(text: str) -> bool:
    return any(ch in VI_ACCENT_CHARS for ch in text)


def test_display_label_known_keys_are_accented_vietnamese():
    assert display_label("transaction_count") == "Số giao dịch"
    assert display_label("gia_tri_can") == "Giá trị cân"
    assert display_label("total_duration_seconds") == "Tổng thời gian downtime"
    assert display_label("loss_group") == "Nhóm tổn thất"


def test_display_label_never_returns_raw_snake_case_for_known_keys():
    for key in ["transaction_count", "gia_tri_can", "sum_gia_tri_can", "avg_duration_seconds"]:
        label = display_label(key)
        assert "_" not in label, f"{key} leaked snake_case: {label}"


def test_display_label_metric_prefix_decomposition():
    assert display_label("sum_gia_tri_can") == "Tổng giá trị cân"


def test_leak_detection_finds_snake_case_and_unaccented():
    assert "transaction_count" in find_internal_keys("Chỉ số transaction_count cao nhất")
    assert find_unaccented_vietnamese("Tong quan du lieu")
    assert find_unaccented_vietnamese("PHAT HIEN")
    assert not find_unaccented_vietnamese("Tổng quan dữ liệu")
    assert not find_internal_keys("Số giao dịch cao nhất tại Cổng 1")


def test_sanitizer_repairs_leaky_table_headers():
    resp = ChatResponse(
        message_id="m",
        conversation_id="c",
        response_type="table",
        title="Kết quả",
        summary="Tổng hợp",
        table=TablePayload(columns=["transaction_count", "gia_tri_can"], rows=[]),
    )
    PublicResponseSanitizer().sanitize(resp)
    assert resp.table.columns == ["Số giao dịch", "Giá trị cân"]
    findings = scan_response(resp)
    assert findings["clean"], findings


def test_sanitizer_flags_unaccented_summary():
    resp = ChatResponse(
        message_id="m",
        conversation_id="c",
        response_type="text",
        title="Tong quan du lieu",
        summary="Phat hien quan trong",
    )
    findings = scan_response(resp)
    assert not findings["clean"]
    assert findings["unaccented_vietnamese"]


def test_request_requirements_downtime_ranking():
    req = build_request_requirements("Máy nào có tổng downtime cao nhất?")
    assert req.required_dimensions == ["machine"]
    assert req.required_metrics == ["downtime_duration"]
    assert "ranked_aggregation" in req.required_capabilities


def test_request_requirements_trend():
    req = build_request_requirements("Phân tích xu hướng downtime theo thời gian.")
    assert "downtime_duration" in req.required_metrics
    assert "event_time" in req.required_datetime_roles
    assert "time_series" in req.required_capabilities


def test_request_requirements_overview_is_empty():
    req = build_request_requirements("Phân tích dữ liệu này.")
    assert not req.required_dimensions and not req.required_metrics


def test_classify_exception_maps_validation_and_timeout():
    assert classify_exception(ValueError("1 validation error for MetricSpec: column is required")) == ErrorCode.QUERY_VALIDATION_FAILED
    assert classify_exception(TimeoutError("query timeout")) == ErrorCode.QUERY_TIMEOUT


def test_customer_error_messages_are_vietnamese_and_clean():
    for code in ErrorCode:
        err = CustomerErrorMessagePolicy.build(code)
        assert _has_vietnamese_accents(err.message), f"{code} message not Vietnamese: {err.message}"
        assert "Exception" not in err.message and "Traceback" not in err.message
        assert not find_internal_keys(err.message), f"{code} leaked internal key"


def test_infrastructure_vs_business_codes():
    assert is_infrastructure(ErrorCode.CATALOG_UNAVAILABLE)
    assert is_infrastructure(ErrorCode.MODEL_UNAVAILABLE)
    assert not is_infrastructure(ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE)
    assert not is_infrastructure(ErrorCode.QUERY_VALIDATION_FAILED)


@pytest.fixture(scope="module")
def service():
    from src.application.chat_service import ChatApplicationService
    from src.config import Settings

    tmp = tempfile.mkdtemp(prefix="gopak_contract_")
    svc = ChatApplicationService(settings=Settings(memory_db_path=Path(tmp) / "contract.db", business_timezone="Asia/Ho_Chi_Minh"))
    if not svc.get_catalog().get("tables"):
        pytest.skip("catalog not built")
    return svc


def _new_convo(service):
    return service.create_conversation(title="contract").id


def test_capability_gate_against_real_production_catalogs(service):
    catalog = service.get_catalog()
    downtime_catalog = {**catalog, "tables": [table for table in catalog.get("tables", []) if table.get("source_id") == "machine_downtime"]}
    apqoee_catalog = {**catalog, "tables": [table for table in catalog.get("tables", []) if table.get("source_id") == "apqoee_cumulative"]}
    downtime = build_dataset_capability_profile(downtime_catalog, "machine_downtime", "Machine Downtime")
    apqoee = build_dataset_capability_profile(apqoee_catalog, "apqoee_cumulative", "APQOEE Cumulative")
    assert "downtime_duration" not in apqoee.metrics
    assert "machine" in downtime.dimensions
    assert "downtime_duration" in downtime.metrics

    req = build_request_requirements("Máy nào có tổng downtime cao nhất?")
    gate = ActiveFileCapabilityGate({"machine_downtime": downtime})
    unsupported = gate.evaluate(req, apqoee)
    assert not unsupported.supported
    assert unsupported.recommended_file_name
    assert _has_vietnamese_accents(unsupported_message(unsupported))
    assert gate.evaluate(req, downtime).supported


def test_production_downtime_routes_without_active_file_or_llm_fallback(service):
    convo = _new_convo(service)
    resp = service.process_message(convo, "Tong downtime ngay 10/11/2025 la bao nhieu?")
    assert resp.metadata.get("sources_used") == ["machine_downtime"]
    assert resp.metadata.get("execution_mode") == "DETERMINISTIC_PRODUCTION"
    assert resp.metadata.get("fallback_used") is False
    assert resp.metadata.get("status") == "COMPLETED"


def test_overview_localization_clean(service):
    convo = _new_convo(service)
    resp = service.process_message(convo, "data co gi")
    blob = " ".join(str(x or "") for x in [resp.title, resp.summary, resp.primary_value])
    assert not find_internal_keys(blob), blob


def test_history_reload_preserves_localization(service):
    convo = _new_convo(service)
    service.process_message(convo, "data co gi")
    detail = service.get_conversation(convo)
    for msg in detail.messages:
        if msg.response is None:
            continue
        blob = " ".join(str(x or "") for x in [msg.response.title, msg.response.summary])
        assert not find_internal_keys(blob), blob


def test_schema_mismatch_does_not_change_health(service):
    before = service.health()
    convo = _new_convo(service)
    service.process_message(convo, "OEE rieng ngay 10/11/2025 la bao nhieu?")
    after = service.health()
    assert before.infrastructure_degraded == after.infrastructure_degraded
    assert after.infrastructure_degraded is False


def test_health_is_layered(service):
    health = service.health()
    assert health.components is not None
    assert health.components.core_api == "HEALTHY"
    if not health.language_model_available:
        assert health.infrastructure_degraded is False
        assert health.components.language_model == "UNAVAILABLE"
