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
    turns = [
        {"id": "t1_top_machine", "message": "Top 5 máy theo tổng downtime.", "expect": {"type": "table", "dimension": None}},
        {"id": "t2_followup", "message": "Kết quả trên nói lên điều gì?", "expect": {"type": "text", "relation": "FOLLOW_UP_ON_PREVIOUS_RESULT"}},
        {"id": "t3_bar", "message": "Vẽ biểu đồ cột top 5 máy theo tổng downtime.", "expect": {"type": "chart", "chart": "bar", "dimension": "machine"}},
        {"id": "t4_trend", "message": "Vẽ biểu đồ line xu hướng downtime theo ngày.", "expect": {"type": "chart", "chart": "line", "dimension": "date"}},
        {"id": "t5_distribution", "message": "Vẽ biểu đồ phân bố số lần dừng theo nhóm tổn thất.", "expect": {"type": "chart", "chart": "pie", "dimension": "loss_group"}},
        {"id": "t6_latest", "message": "Trong tháng gần nhất, top 5 máy theo tổng downtime, số lần dừng, trung bình và tỷ trọng trên tổng downtime.", "expect": {"type": "table", "dimension": None}},
        {"id": "t7_overview_report", "message": "Tạo báo cáo tổng quan về dữ liệu downtime.", "expect": {"type": "report", "dimension": "date"}},
        {"id": "t8_downtime_report", "message": "Tạo báo cáo phân tích downtime gồm KPI, top máy, top nguyên nhân và xu hướng theo ngày.", "expect": {"type": "report", "dimension": "date"}},
    ]
    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gopak-state-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        conversation = app.create_conversation("state-contamination", source_file_id=str(record["id"]))
        seen_plan_ids: set[str] = set()
        seen_result_ids: set[str] = set()
        seen_chart_ids: set[str] = set()
        for turn in turns:
            response = app.process_message(conversation.id, turn["message"], debug=True, source_file_id=str(record["id"]))
            metadata = response.metadata if isinstance(response.metadata, dict) else {}
            contract = metadata.get("request_contract") or {}
            lineage = metadata.get("lineage") or {}
            chart_contract = metadata.get("chart_contract") or {}
            expect = turn["expect"]
            checks = {
                "response_type": response.response_type == expect["type"],
                "lineage_present": all(lineage.get(key) for key in ["turn_id", "request_contract_id", "query_plan_id", "query_result_id", "answer_brief_id", "chart_spec_id", "report_artifact_id"]),
                "unique_plan_id": lineage.get("query_plan_id") not in seen_plan_ids,
                "unique_result_id": lineage.get("query_result_id") not in seen_result_ids,
                "relation": contract.get("relation_to_previous_turn") == expect.get("relation", "NEW_REQUEST"),
            }
            if expect["type"] in {"chart", "report"}:
                checks["chart_contract"] = bool(chart_contract)
                checks["chart_dimension"] = chart_contract.get("dimension") == expect.get("dimension")
                checks["unique_chart_id"] = lineage.get("chart_spec_id") not in seen_chart_ids
            if expect["type"] == "chart":
                checks["chart_type"] = bool(response.chart and response.chart.type == expect.get("chart"))
            if expect.get("relation") == "FOLLOW_UP_ON_PREVIOUS_RESULT":
                checks["grounded_previous_result"] = bool(metadata.get("previous_visible_result_id"))
                checks["no_stale_chart"] = response.chart is None
            if expect["type"] == "report":
                checks["multi_query_report"] = metadata.get("multi_query_execution") is True
                checks["report_complete"] = not (metadata.get("report_completeness") or {}).get("missing")
            observations.append(
                {
                    **turn,
                    "response_type": response.response_type,
                    "title": response.title,
                    "summary": response.summary,
                    "chart": response.chart.model_dump(mode="json") if response.chart else None,
                    "metadata": {
                        "request_contract": contract,
                        "lineage": lineage,
                        "chart_contract": chart_contract,
                        "report_completeness": metadata.get("report_completeness"),
                        "previous_visible_result_id": metadata.get("previous_visible_result_id"),
                    },
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
            seen_plan_ids.add(str(lineage.get("query_plan_id")))
            seen_result_ids.add(str(lineage.get("query_result_id")))
            seen_chart_ids.add(str(lineage.get("chart_spec_id")))
    failures = [item for item in observations if not item["passed"]]
    payload = {
        "summary": {"total": len(observations), "failed": len(failures), "status": "passed" if not failures else "failed"},
        "turns": observations,
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "conversation_state_contamination_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "chart_report_manual_uat.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    raise SystemExit(0 if run()["summary"]["failed"] == 0 else 1)
