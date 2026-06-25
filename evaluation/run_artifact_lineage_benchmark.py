from __future__ import annotations

import json

from state_machine_benchmark_utils import ask, make_app, record, write_artifact


def run() -> dict:
    app, tmp = make_app("gopak-artifact-lineage-")
    try:
        machine = record("Machine_Downtime")
        file_id = str(machine["id"])
        conv = app.create_conversation("artifact lineage", source_file_id=file_id)
        report = ask(app, conv.id, file_id, "Tạo báo cáo tổng quan về dữ liệu downtime.")
        revised = ask(app, conv.id, file_id, "Chi tiết hơn.")
        chart = ask(app, conv.id, file_id, "Vẽ biểu đồ xu hướng tổng downtime theo ngày và nêu 2 điểm đáng chú ý.")
        state = app.memory_service.load_conversation(conv.id)
        report_artifacts = [item for item in state.artifacts if item.artifact_type == "REPORT"]
        checks = {
            "lineage_present_report": bool(report.metadata.get("lineage", {}).get("request_contract_id")),
            "lineage_present_chart": bool(chart.metadata.get("lineage", {}).get("query_result_id")),
            "consistency_passed_report": bool(report.metadata.get("artifact_consistency_validation", {}).get("passed")),
            "consistency_passed_chart": bool(chart.metadata.get("artifact_consistency_validation", {}).get("passed")),
            "report_parent_root": revised.report.parent_report_id == report.report.report_id and revised.report.root_report_id == report.report.root_report_id,
            "state_has_report_artifacts": len(report_artifacts) >= 2,
            "last_visible_is_chart_after_chart_turn": state.last_visible_artifact_type == "CHART",
            "active_report_context_retained": bool(state.active_report_context and state.active_report_context.report_id == revised.report.report_id),
        }
        payload = {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "artifact_count": len(state.artifacts),
            "artifact_types": [item.artifact_type for item in state.artifacts],
            "report_revisions": [item.revision_number for item in report_artifacts],
        }
    finally:
        tmp.cleanup()
    write_artifact("artifact_lineage_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["checks"], ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
