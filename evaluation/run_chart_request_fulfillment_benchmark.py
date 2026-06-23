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
        {
            "id": "chart_top_machine_bar",
            "message": "Vẽ biểu đồ cột top 5 máy theo tổng downtime.",
            "expected_type": "bar",
            "expected_dimension": "machine",
            "expected_metric": "total_downtime",
        },
        {
            "id": "chart_daily_trend_line",
            "message": "Vẽ biểu đồ line xu hướng downtime theo ngày.",
            "expected_type": "line",
            "expected_dimension": "date",
            "expected_metric": "total_downtime",
        },
        {
            "id": "chart_loss_group_distribution",
            "message": "Vẽ biểu đồ phân bố số lần dừng theo nhóm tổn thất.",
            "expected_type": "pie",
            "expected_dimension": "loss_group",
            "expected_metric": "count",
        },
    ]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gopak-chart-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        conversation = app.create_conversation("chart-fulfillment", source_file_id=str(record["id"]))
        for case in cases:
            response = app.process_message(conversation.id, case["message"], debug=True, source_file_id=str(record["id"]))
            contract = response.metadata.get("chart_contract") if isinstance(response.metadata, dict) else {}
            coverage = response.metadata.get("request_coverage") if isinstance(response.metadata, dict) else {}
            values = []
            if response.chart and response.chart.y_keys:
                key = response.chart.y_keys[0]
                values = [row.get(key) for row in response.chart.data if isinstance(row.get(key), (int, float))]
            checks = {
                "is_chart": response.response_type == "chart" and response.chart is not None,
                "chart_type": bool(response.chart and response.chart.type == case["expected_type"]),
                "dimension": contract.get("dimension") == case["expected_dimension"],
                "metric": contract.get("metric") == case["expected_metric"],
                "coverage_complete": not (coverage or {}).get("missing"),
                "current_turn_source": bool(contract.get("source_result_id") and contract.get("source_turn_id")),
                "duration_unit_normalized": case["expected_metric"] != "total_downtime" or contract.get("y_axis_unit") in {"giờ", "phút", "giây"},
                "not_raw_seconds": case["expected_metric"] != "total_downtime" or not values or max(float(v) for v in values) < 10000,
            }
            results.append(
                {
                    **case,
                    "response_type": response.response_type,
                    "chart": response.chart.model_dump(mode="json") if response.chart else None,
                    "chart_contract": contract,
                    "coverage": coverage,
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
    (ARTIFACTS / "chart_request_fulfillment_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run()["summary"]["failed"] == 0 else 1)
