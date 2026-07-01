from __future__ import annotations

from pathlib import Path

from src.application.schemas import ChartPayload, TablePayload
from src.config import Settings
from src.conversation.artifacts import ArtifactType
from src.conversation.state import ConversationState
from src.production.service import ProductionAnalyticsService


def _settings(tmp_path: Path) -> Settings:
    root = Path(__file__).resolve().parents[1]
    return Settings(
        root=root,
        reports_dir=tmp_path / "reports",
        artifacts_dir=tmp_path / "artifacts",
        cache_dir=tmp_path / "cache",
        memory_db_path=tmp_path / "memory.db",
        business_timezone="Asia/Ho_Chi_Minh",
        customer_production_mode=True,
    )


def _seed_state_with_analysis_artifacts() -> ConversationState:
    state = ConversationState(conversation_id="c-report")
    chart = ChartPayload(
        type="line",
        title="Tổng downtime theo ngày",
        x_key="date_label",
        y_keys=["downtime_hours"],
        y_axis_unit="giờ",
        data=[
            {"date_label": "14/11/2025", "downtime_hours": 42.5, "event_count": 9},
            {"date_label": "15/11/2025", "downtime_hours": 12.0, "event_count": 3},
        ],
    )
    state.register_artifact(
        artifact_type=ArtifactType.CHART,
        artifact_id="chart-1",
        turn_id="t-chart",
        payload_snapshot={
            "response_type": "chart",
            "chart": chart.model_dump(mode="json"),
            "metadata": {
                "artifact_created": {
                    "artifact_type": "DAILY_DOWNTIME_CHART",
                    "source": "MACHINE_DOWNTIME",
                    "time_range": {"start": "2025-11-14", "end": "2025-11-15"},
                    "highest_date": "2025-11-14",
                    "highest_value": 42.5,
                }
            },
        },
    )
    apqoee = TablePayload(
        columns=["metric", "value", "unit", "time_scope"],
        rows=[
            {"metric": "Cumulative OEE", "value": 81.2, "unit": "%", "time_scope": "2025-11-14"},
            {"metric": "Cumulative Availability", "value": 88.5, "unit": "%", "time_scope": "2025-11-14"},
        ],
    )
    state.register_artifact(
        artifact_type=ArtifactType.TABLE,
        artifact_id="apqoee-1",
        turn_id="t-apqoee",
        payload_snapshot={
            "response_type": "table",
            "table": apqoee.model_dump(mode="json"),
            "metadata": {"artifact_created": {"artifact_type": "APQOEE_SNAPSHOT", "source": "APQOEE_CUMULATIVE", "as_of_date": "2025-11-14"}},
        },
    )
    return state


def _remember_report(state: ConversationState, response) -> None:
    assert response.report is not None
    state.register_artifact(
        artifact_type=ArtifactType.REPORT,
        artifact_id=response.report.report_id,
        turn_id=response.metadata["lineage"]["turn_id"],
        parent_artifact_id=response.report.parent_report_id,
        root_artifact_id=response.report.root_report_id,
        revision_number=response.report.revision_number,
        payload_snapshot=response.report.model_dump(mode="json"),
        pdf_artifact_id=response.downloads[0].id if response.downloads else None,
    )


def test_report_workflow_create_revise_export_query_preserves_fact_hash(tmp_path: Path, monkeypatch) -> None:
    service = ProductionAnalyticsService(_settings(tmp_path))
    state = _seed_state_with_analysis_artifacts()
    calls: list[str] = []

    def fake_commentary(purpose: str, facts: dict):
        calls.append(purpose)
        return "- Nhận xét quản lý dựa trên snapshot fact đã xác minh.\n- Không thay đổi số liệu nguồn trong báo cáo.", True

    monkeypatch.setattr(service, "_grounded_commentary", fake_commentary)

    create = service.process("c-report", "Tạo báo cáo quản lý từ toàn bộ kết quả vừa phân tích.", context={"state": state})
    assert create.response_type == "report"
    assert create.metadata["production_turn_trace"]["resolved_intent"] == "REPORT_CREATE"
    assert create.metadata["production_turn_trace"]["llm_called"] is True
    assert create.report is not None
    assert create.report.revision_number == 1
    assert create.report.completeness["fact_hash"]
    assert create.metadata["report_validation"]["passed"] is True
    assert create.downloads and create.downloads[0].filename.startswith("report_")
    fact_hash = create.report.completeness["fact_hash"]
    _remember_report(state, create)

    revise = service.process("c-report", "Viết phần nhận xét quản lý chi tiết hơn.", context={"state": state})
    assert revise.response_type == "report"
    assert revise.metadata["production_turn_trace"]["resolved_intent"] == "REPORT_REVISE"
    assert revise.metadata["production_turn_trace"]["revision_operations"] == ["management_detail"]
    assert revise.metadata["production_turn_trace"]["llm_called"] is True
    assert revise.report is not None
    assert revise.report.revision_number == 2
    assert revise.report.completeness["fact_hash"] == fact_hash
    _remember_report(state, revise)

    title = service.process("c-report", "Đổi tiêu đề thành Báo cáo tình hình sản xuất ngày 14/11/2025.", context={"state": state})
    assert title.report is not None
    assert title.report.title == "Báo cáo tình hình sản xuất ngày 14/11/2025"
    assert title.report.completeness["fact_hash"] == fact_hash
    _remember_report(state, title)

    export = service.process("c-report", "Xuất phiên bản hiện tại ra PDF.", context={"state": state})
    assert export.response_type == "report"
    assert export.metadata["production_turn_trace"]["resolved_intent"] == "REPORT_EXPORT"
    assert export.report is not None
    assert export.report.revision_number == title.report.revision_number
    assert export.downloads and export.downloads[0].mime_type == "application/pdf"

    query = service.process("c-report", "Báo cáo này đang sử dụng những nguồn dữ liệu nào?", context={"state": state})
    assert query.response_type == "table"
    assert query.metadata["production_turn_trace"]["resolved_intent"] == "REPORT_QUERY"
    assert query.table is not None
    assert query.table.rows

    remove_and_export = service.process("c-report", "Bỏ phần giới hạn phân tích rồi xuất lại PDF.", context={"state": state})
    assert remove_and_export.response_type == "report"
    assert remove_and_export.metadata["production_turn_trace"]["resolved_intent"] == "REPORT_REVISE_EXPORT"
    assert remove_and_export.metadata["production_turn_trace"]["revision_operations"] == ["remove_limitations"]
    assert remove_and_export.report is not None
    assert remove_and_export.report.limitations == []
    assert remove_and_export.report.completeness["fact_hash"] == fact_hash
    assert remove_and_export.downloads
    assert "report_revision_validation" in calls


def test_report_top_machine_revision_does_not_fabricate_missing_artifact(tmp_path: Path, monkeypatch) -> None:
    service = ProductionAnalyticsService(_settings(tmp_path))
    state = _seed_state_with_analysis_artifacts()
    monkeypatch.setattr(service, "_grounded_commentary", lambda purpose, facts: ("- Nhận xét hợp lệ theo snapshot fact.", True))

    create = service.process("c-report", "Tạo báo cáo quản lý từ toàn bộ kết quả vừa phân tích.", context={"state": state})
    _remember_report(state, create)
    response = service.process("c-report", "Thêm bảng top 5 máy có downtime cao nhất.", context={"state": state})

    assert response.response_type == "report"
    assert response.report is not None
    section = next(item for item in response.report.sections if item.section_type == "top_machines_missing")
    assert "không tự tạo bảng số liệu mới" in (section.summary or "")
    assert section.table is None


def test_report_create_uses_public_apqoee_snapshot_for_kpis(tmp_path: Path, monkeypatch) -> None:
    service = ProductionAnalyticsService(_settings(tmp_path))
    state = ConversationState(conversation_id="c-report")
    monkeypatch.setattr(service, "_grounded_commentary", lambda purpose, facts: ("- Nhận xét hợp lệ theo snapshot fact.", True))
    state.register_artifact(
        artifact_type=ArtifactType.TABLE,
        artifact_id="apqoee-public-1",
        turn_id="t-apqoee-public",
        payload_snapshot={
            "response_type": "table",
            "table": {
                "columns": ["Chỉ số", "Giá trị"],
                "rows": [
                    {"Chỉ số": "OEE tích lũy", "Giá trị": "81,20%"},
                    {"Chỉ số": "Availability tích lũy", "Giá trị": "88,50%"},
                ],
            },
            "metadata": {
                "production_turn_trace": {
                    "artifact_created": {
                        "artifact_type": "APQOEE_SNAPSHOT",
                        "source": "APQOEE_CUMULATIVE",
                        "as_of_date": "2025-11-14",
                    }
                }
            },
        },
    )

    response = service.process("c-report", "Tạo báo cáo quản lý từ toàn bộ kết quả vừa phân tích.", context={"state": state})

    assert response.response_type == "report"
    assert response.report is not None
    assert response.report.kpis
    assert response.report.kpis[0].label == "OEE tích lũy"
    assert response.report.kpis[0].value == "81,20"
    assert response.report.kpis[0].unit == "%"
