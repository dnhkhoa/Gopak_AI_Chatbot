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


def _machine_file() -> dict[str, Any]:
    return next(
        item
        for item in list_uploaded_files()
        if "Machine_Downtime" in str(item.get("filename", "")) and item.get("status") == "ready"
    )


def run() -> dict[str, Any]:
    settings = get_settings()
    record = _machine_file()
    cases = [
        {"id": "overview_report", "message": "Tạo báo cáo tổng quan về dữ liệu downtime."},
        {"id": "downtime_report", "message": "Tạo báo cáo phân tích downtime gồm KPI, top máy, top nguyên nhân và xu hướng theo ngày."},
    ]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gopak-report-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        conversation = app.create_conversation("report-orchestration", source_file_id=str(record["id"]))
        for case in cases:
            response = app.process_message(conversation.id, case["message"], debug=True, source_file_id=str(record["id"]))
            completeness = response.metadata.get("report_completeness") if isinstance(response.metadata, dict) else {}
            statuses = response.metadata.get("report_section_statuses") if isinstance(response.metadata, dict) else {}
            pdf_meta = response.metadata.get("pdf_report") if isinstance(response.metadata, dict) else {}
            download_suffixes = {Path(item.filename).suffix.lower() for item in response.downloads}
            checks = {
                "is_report": response.response_type == "report",
                "multi_query": response.metadata.get("multi_query_execution") is True,
                "has_table": response.table is not None and bool(response.table.rows),
                "has_chart": response.chart is not None and response.chart.type == "line",
                "single_pdf_download": download_suffixes == {".pdf"},
                "no_html_xlsx_downloads": not ({".html", ".xlsx"} & download_suffixes),
                "pdf_ready": bool(response.report and response.report.pdf_status == "ready" and pdf_meta.get("status") == "ready"),
                "complete": not completeness.get("missing"),
                "has_required_sections": all(section in statuses for section in completeness.get("required", [])),
                "chart_contract_current": bool((response.metadata.get("chart_contract") or {}).get("source_result_id")),
            }
            results.append(
                {
                    **case,
                    "response_type": response.response_type,
                    "title": response.title,
                    "summary": response.summary,
                    "downloads": [item.model_dump(mode="json") for item in response.downloads],
                    "report_completeness": completeness,
                    "report_section_statuses": statuses,
                    "pdf_report": pdf_meta,
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    failures = [item for item in results if not item["passed"]]
    payload = {
        "summary": {"total": len(results), "failed": len(failures), "status": "passed" if not failures else "failed"},
        "results": results,
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "report_orchestration_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=True, indent=2))
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run()["summary"]["failed"] == 0 else 1)
