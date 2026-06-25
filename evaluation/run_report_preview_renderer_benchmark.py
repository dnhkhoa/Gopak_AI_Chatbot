from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files

ARTIFACTS = ROOT / "artifacts"
EXPECTED_SECTIONS = [
    "dataset_overview",
    "kpi_total_downtime",
    "kpi_stop_count",
    "top_machines",
    "top_causes",
    "time_trend",
    "management_commentary",
    "source_filters_limitations",
]


def run() -> dict[str, Any]:
    settings = get_settings()
    record = next(item for item in list_uploaded_files() if "Machine_Downtime" in str(item.get("filename", "")) and item.get("status") == "ready")
    with tempfile.TemporaryDirectory(prefix="gopak-report-preview-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        conversation = app.create_conversation("report-preview", source_file_id=str(record["id"]))
        response = app.process_message(
            conversation.id,
            "Tạo báo cáo phân tích downtime gồm KPI, top máy, top nguyên nhân và xu hướng theo ngày.",
            debug=True,
            source_file_id=str(record["id"]),
        )
        history = app.public_conversation_detail(app.get_conversation(conversation.id, 20))
    report = response.report
    section_types = [section.section_type for section in report.sections] if report else []
    history_response = history.messages[-1].response if history and history.messages else None
    history_report = history_response.report if history_response else None
    coverage = {
        "requested_sections": len(EXPECTED_SECTIONS),
        "backend_sections": len(section_types),
        "rendered_sections": len(section_types),
        "missing_sections": [section for section in EXPECTED_SECTIONS if section not in section_types],
    }
    summary = {
        "report_dispatched_as_chart": int(response.response_type != "report" or report is None),
        "report_missing_rendered_sections": int(bool(coverage["missing_sections"]) or coverage["rendered_sections"] != len(EXPECTED_SECTIONS)),
        "history_response_type_mutation": int(not history_response or history_response.response_type != "report"),
        "history_report_payload_missing": int(not history_report or len(history_report.sections) != len(EXPECTED_SECTIONS)),
        "report_has_chart_for_compatibility": int(response.chart is not None),
        "status": "passed",
    }
    summary["status"] = "passed" if all(
        summary[key] == 0 for key in [
            "report_dispatched_as_chart",
            "report_missing_rendered_sections",
            "history_response_type_mutation",
            "history_report_payload_missing",
        ]
    ) and summary["report_has_chart_for_compatibility"] == 1 else "failed"
    payload = {
        "summary": summary,
        "coverage": coverage,
        "response_type": response.response_type,
        "history_response_type": history_response.response_type if history_response else None,
        "section_types": section_types,
        "history_section_types": [section.section_type for section in history_report.sections] if history_report else [],
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "report_preview_renderer_benchmark.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return payload


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["summary"]["status"] == "passed" else 1)
