from __future__ import annotations

import json

from pdf_report_benchmark_utils import EXPECTED_PUBLIC_SECTIONS, REPORT_QUESTION, report_app, write_artifact


def run() -> dict:
    with report_app() as (app, record, _tmp):
        conversation = app.create_conversation("pdf-report-persistence", source_file_id=str(record["id"]))
        response = app.process_message(conversation.id, REPORT_QUESTION, debug=True, source_file_id=str(record["id"]))
        public_detail = app.public_conversation_detail(app.get_conversation(conversation.id, 20))
        last_response = public_detail.messages[-1].response if public_detail and public_detail.messages else None
        last_report = last_response.report if last_response else None
        original_pdf = app.resolve_artifact(response.downloads[0].id) if response.downloads else None
        persisted_pdf = app.resolve_artifact(last_response.downloads[0].id) if last_response and last_response.downloads else None
        checks = {
            "created_report_once": response.response_type == "report" and response.report is not None,
            "history_response_still_report": bool(last_response and last_response.response_type == "report"),
            "history_report_payload_present": last_report is not None,
            "same_report_id": bool(last_report and response.report and last_report.report_id == response.report.report_id),
            "same_pdf_download": bool(last_response and response.downloads and last_response.downloads and last_response.downloads[0].id == response.downloads[0].id),
            "pdf_resolves_after_reload": bool(original_pdf and original_pdf.exists() and persisted_pdf and persisted_pdf.exists()),
            "source_file_retained": bool(last_report and response.report and last_report.source_file_name == response.report.source_file_name),
            "sections_retained": bool(last_report and [section.section_type for section in last_report.sections] == EXPECTED_PUBLIC_SECTIONS),
            "public_history_metadata_safe": bool(last_response and set(last_response.metadata).issubset({"active_file_id", "active_file_name", "file_scope_validated"})),
        }
        payload = {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "conversation_id": conversation.id,
            "report_id": response.report.report_id if response.report else None,
            "pdf_artifact": str(original_pdf) if original_pdf else None,
            "persisted_pdf_artifact": str(persisted_pdf) if persisted_pdf else None,
            "history_message_count": len(public_detail.messages) if public_detail else 0,
        }
    write_artifact("pdf_persistence_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
