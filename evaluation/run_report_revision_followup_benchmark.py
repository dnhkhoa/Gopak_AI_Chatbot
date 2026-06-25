from __future__ import annotations

import json

from state_machine_benchmark_utils import ask, make_app, record, write_artifact


def run() -> dict:
    app, tmp = make_app("gopak-report-revision-")
    try:
        machine = record("Machine_Downtime")
        file_id = str(machine["id"])
        conv = app.create_conversation("report revision replay", source_file_id=file_id)
        turns = [
            "Tạo báo cáo tổng quan về dữ liệu downtime.",
            "Chi tiết hơn.",
            "Rút gọn còn 1-2 trang.",
            "Xuất PDF.",
        ]
        responses = [ask(app, conv.id, file_id, turn) for turn in turns]
        checks = {
            "all_report": all(resp.response_type == "report" for resp in responses),
            "no_metric_clarification": all(resp.response_type != "clarification" for resp in responses[1:]),
            "revision_numbers": [resp.report.revision_number if resp.report else None for resp in responses] == [1, 2, 3, 3],
            "detail_levels": [resp.report.detail_level if resp.report else None for resp in responses] == ["STANDARD", "DETAILED", "COMPACT", "COMPACT"],
            "export_uses_current_report": responses[-1].report.report_id == responses[-2].report.report_id,
            "pdf_only": all(len(resp.downloads) == 1 and resp.downloads[0].mime_type == "application/pdf" for resp in responses),
            "artifact_routes": [resp.metadata.get("execution_mode") for resp in responses[1:]] == ["ARTIFACT_REVISION", "ARTIFACT_REVISION", "ARTIFACT_EXPORT"],
        }
        state = app.memory_service.load_conversation(conv.id)
        payload = {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "response_types": [resp.response_type for resp in responses],
            "execution_modes": [resp.metadata.get("execution_mode") for resp in responses],
            "last_visible_artifact_type": state.last_visible_artifact_type,
            "active_report_revision": state.active_report_context.revision_number if state.active_report_context else None,
        }
    finally:
        tmp.cleanup()
    write_artifact("report_revision_followup_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["checks"], ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
