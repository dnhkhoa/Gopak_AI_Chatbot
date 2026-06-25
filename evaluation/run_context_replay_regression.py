from __future__ import annotations

import json

from state_machine_benchmark_utils import ask, make_app, record, write_artifact


def run() -> dict:
    app, tmp = make_app("gopak-context-replay-")
    try:
        machine = record("Machine_Downtime")
        entry = record("EntryTransaction")
        machine_id = str(machine["id"])
        entry_id = str(entry["id"])
        results = []

        conv_a = app.create_conversation("sequence-a", source_file_id=machine_id)
        a1 = ask(app, conv_a.id, machine_id, "Top 5 máy theo tổng downtime.")
        a2 = ask(app, conv_a.id, machine_id, "Nhận xét kết quả vừa rồi.")
        a3 = ask(app, conv_a.id, machine_id, "Vẽ chart cho kết quả đó.")
        a4 = ask(app, conv_a.id, machine_id, "Nguyên nhân nào có tổng downtime cao nhất?")
        a5 = ask(app, conv_a.id, machine_id, "Nhận xét kết quả mới.")
        results.append({
            "sequence": "A",
            "passed": a1.response_type in {"table", "chart"} and a2.response_type == "text" and a3.response_type == "chart" and a4.response_type in {"table", "scalar"} and a5.response_type == "text",
            "types": [a1.response_type, a2.response_type, a3.response_type, a4.response_type, a5.response_type],
        })

        conv_b = app.create_conversation("sequence-b", source_file_id=machine_id)
        b1 = ask(app, conv_b.id, machine_id, "Vẽ biểu đồ xu hướng downtime theo ngày.")
        b2 = ask(app, conv_b.id, machine_id, "Nêu 2 insight từ kết quả này.")
        b3 = ask(app, conv_b.id, machine_id, "Đổi sang phân bố nguyên nhân.")
        b4 = ask(app, conv_b.id, machine_id, "Quay lại trend theo ngày.")
        results.append({
            "sequence": "B",
            "passed": b1.response_type == "chart" and b2.response_type == "text" and b3.response_type in {"chart", "table"} and b4.response_type == "chart",
            "types": [b1.response_type, b2.response_type, b3.response_type, b4.response_type],
        })

        conv_f = app.create_conversation("sequence-f", source_file_id=entry_id)
        f1 = ask(app, conv_f.id, entry_id, "Máy nào có tổng downtime cao nhất?")
        conv_f2 = app.create_conversation("sequence-f-machine", source_file_id=machine_id)
        f2 = ask(app, conv_f2.id, machine_id, "Máy nào có tổng downtime cao nhất?")
        results.append({
            "sequence": "F",
            "passed": f1.response_type == "refusal" and f1.metadata.get("error_code") == "UNSUPPORTED_BY_ACTIVE_FILE" and f2.response_type in {"scalar", "table"},
            "types": [f1.response_type, f2.response_type],
            "error_code": f1.metadata.get("error_code"),
        })

        conv_g = app.create_conversation("sequence-g", source_file_id=machine_id)
        g1 = ask(app, conv_g.id, machine_id, "vẽ biêu đồ xu hươong dowtime theo ngày")
        results.append({
            "sequence": "G",
            "passed": g1.response_type == "chart" and g1.chart is not None and g1.chart.type == "line",
            "types": [g1.response_type],
            "chart_type": g1.chart.type if g1.chart else None,
        })

        payload = {
            "status": "passed" if all(item["passed"] for item in results) else "failed",
            "results": results,
            "failed": [item for item in results if not item["passed"]],
        }
    finally:
        tmp.cleanup()
    write_artifact("context_replay_regression_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "failed": result["failed"]}, ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
