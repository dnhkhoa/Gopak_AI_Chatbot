"""Contract tests for the unified localization / capability / error / health gates.

These run on EVERY response path so a regression in any single builder fails CI,
covering spec section 17.3 + 18 (Tests A-I). Catalog-dependent end-to-end tests
skip gracefully if the demo files / cache are not present.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.application.capability import (
    ActiveFileCapabilityGate,
    build_dataset_capability_profile,
    build_request_requirements,
    unsupported_message,
)
from src.application.errors import (
    CustomerErrorMessagePolicy,
    ErrorCode,
    classify_exception,
    is_infrastructure,
)
from src.application.public_response import PublicResponseSanitizer, scan_response
from src.application.schemas import ChatResponse, TablePayload
from src.rendering.labels import (
    display_label,
    find_internal_keys,
    find_unaccented_vietnamese,
)

ENTRY_TRANSACTION = "2ad2989784fc41ffb9fef3225034db54"
LOSS_ASSIGNMENT = "a329169db4984cab80ed5fea5880bb4f"
MACHINE_DOWNTIME = "e385c6e2a4ff41a8baf63f323dfc0b59"

VI_ACCENT_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
                      "ĂÂĐÊÔƠƯ")


def _has_vietnamese_accents(text: str) -> bool:
    return any(ch in VI_ACCENT_CHARS for ch in text)


# --- P0-A: display label registry -------------------------------------------

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
    # clean Vietnamese must NOT trip the detector
    assert not find_unaccented_vietnamese("Tổng quan dữ liệu")
    assert not find_internal_keys("Số giao dịch cao nhất tại Cổng 1")


def test_sanitizer_repairs_leaky_table_headers():
    resp = ChatResponse(
        message_id="m", conversation_id="c", response_type="table",
        title="Kết quả", summary="Tổng hợp",
        table=TablePayload(columns=["transaction_count", "gia_tri_can"], rows=[]),
    )
    PublicResponseSanitizer().sanitize(resp)
    assert resp.table.columns == ["Số giao dịch", "Giá trị cân"]
    findings = scan_response(resp)
    assert findings["clean"], findings


def test_sanitizer_flags_unaccented_summary():
    resp = ChatResponse(
        message_id="m", conversation_id="c", response_type="text",
        title="Tong quan du lieu", summary="Phat hien quan trong",
    )
    findings = scan_response(resp)
    assert not findings["clean"]
    assert findings["unaccented_vietnamese"]


# --- P0-B: capability gate ---------------------------------------------------

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


# --- error taxonomy / policy -------------------------------------------------

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


# --- end-to-end (catalog dependent) -----------------------------------------

@pytest.fixture(scope="module")
def service():
    from src.config import Settings
    from src.application.chat_service import ChatApplicationService
    from src.files.upload_store import find_uploaded_file

    if not find_uploaded_file(ENTRY_TRANSACTION):
        pytest.skip("demo files not available")
    tmp = tempfile.mkdtemp(prefix="gopak_contract_")
    svc = ChatApplicationService(settings=Settings(memory_db_path=Path(tmp) / "contract.db"))
    if not svc.get_catalog().get("tables"):
        pytest.skip("catalog not built")
    return svc


def _new_convo(service, file_id):
    convo = service.create_conversation(title="contract", source_file_id=file_id)
    return convo.id


def test_capability_gate_against_real_catalogs(service):
    entry = build_dataset_capability_profile(service.get_catalog_for_file(ENTRY_TRANSACTION), ENTRY_TRANSACTION, "EntryTransaction")
    downtime = build_dataset_capability_profile(service.get_catalog_for_file(MACHINE_DOWNTIME), MACHINE_DOWNTIME, "Machine_Downtime")
    assert "machine" not in entry.dimensions
    assert "downtime_duration" not in entry.metrics
    assert "machine" in downtime.dimensions
    assert "downtime_duration" in downtime.metrics

    req = build_request_requirements("Máy nào có tổng downtime cao nhất?")
    gate = ActiveFileCapabilityGate({MACHINE_DOWNTIME: downtime})
    unsupported = gate.evaluate(req, entry)
    assert not unsupported.supported
    assert unsupported.recommended_file_name
    assert _has_vietnamese_accents(unsupported_message(unsupported))
    # same question on the right file is supported
    assert gate.evaluate(req, downtime).supported


def test_wrong_file_downtime_returns_unsupported_no_sql_no_llm(service):
    convo = _new_convo(service, ENTRY_TRANSACTION)
    resp = service.process_message(convo, "Máy nào có tổng downtime cao nhất?", source_file_id=ENTRY_TRANSACTION)
    assert resp.metadata.get("error_code") == ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE.value
    assert resp.metadata.get("llm_called") is False
    assert resp.metadata.get("generated_sql") in (None, "")
    assert resp.metadata.get("is_infrastructure") is not True
    assert _has_vietnamese_accents(resp.summary)
    assert not find_internal_keys(resp.summary)


def test_wrong_file_trend_returns_unsupported(service):
    convo = _new_convo(service, ENTRY_TRANSACTION)
    resp = service.process_message(convo, "Phân tích xu hướng downtime theo thời gian.", source_file_id=ENTRY_TRANSACTION)
    assert resp.metadata.get("error_code") == ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE.value


def test_supported_file_downtime_not_blocked(service):
    convo = _new_convo(service, MACHINE_DOWNTIME)
    resp = service.process_message(convo, "Máy nào có tổng downtime cao nhất?", source_file_id=MACHINE_DOWNTIME)
    assert resp.metadata.get("error_code") != ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE.value


def test_overview_localization_clean(service):
    convo = _new_convo(service, ENTRY_TRANSACTION)
    resp = service.process_message(convo, "Phân tích dữ liệu này và cho tôi ba phát hiện quan trọng nhất.", source_file_id=ENTRY_TRANSACTION)
    blob = " ".join(str(x or "") for x in [resp.title, resp.summary, resp.primary_value])
    assert not find_internal_keys(blob), blob
    assert not find_unaccented_vietnamese(blob), blob


def test_history_reload_preserves_localization(service):
    convo = _new_convo(service, ENTRY_TRANSACTION)
    service.process_message(convo, "Phân tích dữ liệu này.", source_file_id=ENTRY_TRANSACTION)
    detail = service.get_conversation(convo)
    for msg in detail.messages:
        if msg.response is None:
            continue
        blob = " ".join(str(x or "") for x in [msg.response.title, msg.response.summary])
        assert not find_internal_keys(blob), blob
        assert not find_unaccented_vietnamese(blob), blob


def test_schema_mismatch_does_not_change_health(service):
    before = service.health()
    convo = _new_convo(service, ENTRY_TRANSACTION)
    service.process_message(convo, "Máy nào có tổng downtime cao nhất?", source_file_id=ENTRY_TRANSACTION)
    after = service.health()
    assert before.infrastructure_degraded == after.infrastructure_degraded
    assert after.infrastructure_degraded is False


def test_health_is_layered(service):
    health = service.health()
    assert health.components is not None
    assert health.components.core_api == "HEALTHY"
    # model state must not flip the infrastructure banner
    if not health.language_model_available:
        assert health.infrastructure_degraded is False
        assert health.components.language_model == "UNAVAILABLE"
