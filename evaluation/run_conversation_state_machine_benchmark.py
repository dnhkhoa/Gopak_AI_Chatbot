from __future__ import annotations

import json

from state_machine_benchmark_utils import ask, make_app, record, write_artifact


def run() -> dict:
    app, tmp = make_app("gopak-conversation-state-")
    try:
        machine = record("Machine_Downtime")
        file_id = str(machine["id"])
        conv = app.create_conversation("conversation state machine", source_file_id=file_id)
        clarification = ask(app, conv.id, file_id, "vẽ biểu đồ")
        new_request = ask(app, conv.id, file_id, "Tạo báo cáo tổng quan về dữ liệu downtime.")
        detail = ask(app, conv.id, file_id, "Chi tiết hơn.")
        export = ask(app, conv.id, file_id, "Xuất PDF.")
        state = app.memory_service.load_conversation(conv.id)
        checks = {
            "clarification_started": clarification.response_type == "clarification",
            "new_request_bypasses_old_clarification": new_request.response_type == "report",
            "pending_cleared": state.pending_clarification is None,
            "detail_is_revision": detail.response_type == "report" and detail.metadata.get("execution_mode") == "ARTIFACT_REVISION",
            "export_is_artifact_export": export.response_type == "report" and export.metadata.get("execution_mode") == "ARTIFACT_EXPORT",
            "last_visible_report": state.last_visible_artifact_type == "REPORT",
            "state_version_incremented": state.state_version >= 4,
        }
        payload = {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "response_types": [clarification.response_type, new_request.response_type, detail.response_type, export.response_type],
            "execution_modes": [resp.metadata.get("execution_mode") for resp in [clarification, new_request, detail, export]],
            "turn_resolutions": [resp.metadata.get("turn_resolution") for resp in [new_request, detail, export]],
            "state_version": state.state_version,
        }
    finally:
        tmp.cleanup()
    write_artifact("conversation_state_machine_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["checks"], ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
