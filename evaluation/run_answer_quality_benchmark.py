"""Answer-quality + multi-part intent benchmark.

Scores each case on concrete, deterministic requirements (intent, metric, dimension, top-N,
derived metric, requested output, commentary, source accuracy, clarification necessity/
specificity) rather than only checking that answers are longer. Runs in-process through the
real ChatApplicationService pipeline (create_conversation -> set_active_file -> process_message),
so it exercises routing, planning, safe SQL and presentation exactly like the product.

Outputs:
  artifacts/answer_quality_results.json   - per-case scoring across all categories
  artifacts/multipart_intent_results.json - requirement coverage for multi-part cases
"""
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
GENERIC_CLARIFICATIONS = {
    "Bạn muốn mình nhận xét dựa trên kết quả nào? Hãy hỏi một bảng, biểu đồ hoặc thống kê cụ thể trước.",
    "Bạn muốn xem tổng quan dữ liệu, schema, dữ liệu mẫu hay một thống kê cụ thể?",
}


def _cases() -> list[dict[str, Any]]:
    return [
        # scalar
        {"id": "AQ-scalar", "category": "scalar", "file": "machine",
         "turns": [{"m": "File có bao nhiêu bản ghi?", "expect": {"type": "scalar", "no_sql_ok": True}}]},
        # overview
        {"id": "AQ-overview", "category": "overview", "file": "loss",
         "turns": [{"m": "File này chứa dữ liệu gì?", "expect": {"type": "data_overview", "table": True}}]},
        # ranking
        {"id": "AQ-ranking", "category": "ranking", "file": "machine",
         "turns": [{"m": "Cho tôi top 5 máy theo tổng thời gian downtime.", "expect": {"type": "table", "table": True, "limit": 5, "dimension": "may", "sql": True}}]},
        # multi-metric
        {"id": "AQ-multimetric", "category": "multi_metric", "file": "machine",
         "turns": [{"m": "Top 5 máy theo tổng downtime, thêm số lần dừng và thời lượng trung bình.", "expect": {"type": "table", "table": True, "limit": 5, "multi_metric": True, "sql": True}}]},
        # multi-part (the headline case)
        {"id": "AQ-multipart-1", "category": "multi_part", "file": "loss",
         "turns": [{"m": "Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét những điểm đáng chú ý trong kết quả.",
                    "expect": {"type_any": ["table", "chart"], "table": True, "dimension": "nhom", "percentage": True, "commentary": True, "sql": True},
                    "requirements": ["top_n", "group_count", "percentage", "table", "commentary"]}]},
        {"id": "AQ-multipart-2", "category": "multi_part", "file": "loss",
         "turns": [{"m": "Cho tôi top 3 loại tổn thất, tỷ lệ trên tổng và giải thích ngắn gọn.",
                    "expect": {"type_any": ["table", "chart"], "table": True, "limit": 3, "percentage": True, "commentary": True, "sql": True},
                    "requirements": ["top_n", "percentage", "table", "commentary"]}]},
        {"id": "AQ-multipart-3", "category": "multi_part", "file": "machine",
         "turns": [{"m": "Nhận xét top 5 máy theo tổng downtime trong tháng gần nhất.",
                    "expect": {"type_any": ["table", "chart"], "table": True, "dimension": "may", "time_filter": True, "commentary": True, "sql": True},
                    "requirements": ["top_n", "time_filter", "commentary", "table"]}]},
        # chart request
        {"id": "AQ-chart", "category": "chart_request", "file": "machine",
         "turns": [{"m": "Vẽ biểu đồ top 5 máy có tổng downtime cao nhất.", "expect": {"type": "chart", "chart": True, "limit": 5, "sql": True}}]},
        # commentary follow-up (must not create a new query)
        {"id": "AQ-followup", "category": "commentary_followup", "file": "machine",
         "turns": [
             {"m": "Cho tôi top 5 máy theo tổng thời gian downtime.", "expect": {"type": "table", "table": True}},
             {"m": "Nhận xét bảng vừa rồi.", "expect": {"type": "text", "commentary": True}},
         ]},
        # commentary + new query (must produce analytics, not follow-up-only)
        {"id": "AQ-commentary-new", "category": "commentary_plus_query", "file": "machine",
         "turns": [{"m": "Nhận xét top 5 nguyên nhân theo số lần ghi nhận.", "expect": {"type_any": ["table", "chart"], "table": True, "commentary": True, "sql": True}}]},
        # ambiguous dimension - single confident mapping -> no clarification
        {"id": "AQ-dim", "category": "ambiguous_dimension", "file": "loss",
         "turns": [{"m": "Top 5 nhóm tổn thất theo số lần ghi nhận.", "expect": {"type": "table", "table": True, "dimension": "nhom", "sql": True}}]},
        # ambiguous metric (bare ranking) - acceptable: resolves to a sensible default table (no generic clarification)
        {"id": "AQ-metric", "category": "ambiguous_metric", "file": "machine",
         "turns": [{"m": "Máy nào nhiều nhất?", "expect": {"not_generic_clarification": True}}]},
        # topic restore
        {"id": "AQ-topic", "category": "topic_restore", "file": "machine",
         "turns": [
             {"m": "Cho tôi top 5 máy có tổng downtime cao nhất trong tháng gần nhất.", "expect": {"type_any": ["table", "chart"], "time_filter": True}},
             {"m": "File này có những cột nào?", "expect": {"type": "schema"}},
             {"m": "Quay lại phần top máy lúc nãy.", "expect": {"type_any": ["table", "chart"], "time_filter": True}},
         ]},
    ]


def _record(files: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    needles = {"machine": "Machine_Downtime", "loss": "Loss_Assignment", "entry": "EntryTransaction"}
    return next((item for item in files if needles[key] in str(item.get("filename", ""))), None)


def _ascii(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", str(text).lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _table_text(response: Any) -> str:
    if not response.table:
        return ""
    return _ascii(json.dumps(response.table.model_dump(), ensure_ascii=False))


def _score(response: Any, expect: dict[str, Any]) -> dict[str, bool]:
    md = response.metadata or {}
    summary = (response.summary or "")
    table_text = _table_text(response)
    checks: dict[str, bool] = {}
    if "type" in expect:
        checks["intent"] = response.response_type == expect["type"]
    if "type_any" in expect:
        checks["intent"] = response.response_type in set(expect["type_any"])
    if expect.get("table"):
        checks["table"] = bool(response.table and response.table.rows)
    if expect.get("chart"):
        checks["chart"] = bool(response.chart)
    if "limit" in expect:
        rows = len(response.table.rows) if response.table else 0
        checks["top_n"] = 0 < rows <= expect["limit"]
    if expect.get("multi_metric"):
        cols = len(response.table.columns) if response.table else 0
        checks["multi_metric"] = cols >= 3
    if "dimension" in expect:
        checks["dimension"] = expect["dimension"] in table_text or expect["dimension"] in _ascii(summary)
    if expect.get("percentage"):
        checks["percentage"] = "%" in table_text or "%" in summary
    if expect.get("time_filter"):
        # latest-month machine ranking is materially smaller than the all-time top (413,57h)
        checks["time_filter"] = "413,57" not in summary
    if expect.get("commentary"):
        checks["commentary"] = bool(md.get("commentary_attached")) or response.response_type == "text" or "nhận xét" in summary.lower()
    if "sql" in expect:
        sql_present = bool(md.get("generated_sql") or ((md.get("debug") or {}).get("sql") if isinstance(md.get("debug"), dict) else None))
        checks["sql"] = sql_present == expect["sql"]
    if expect.get("no_sql_ok"):
        checks["intent_present"] = bool(summary or response.primary_value or response.table)
    if expect.get("not_generic_clarification"):
        checks["not_generic_clarification"] = summary not in GENERIC_CLARIFICATIONS
    # source accuracy: never leak generic clarification when a concrete answer is expected
    if response.response_type == "clarification" and not expect.get("clarification"):
        checks["no_unwanted_clarification"] = summary not in GENERIC_CLARIFICATIONS
    return checks


def run() -> dict[str, Any]:
    ARTIFACTS.mkdir(exist_ok=True)
    files = list_uploaded_files()
    settings = get_settings()
    results: list[dict[str, Any]] = []
    multipart: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gopak-answer-quality-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(db_path=Path(tmp) / "m.db", cache_root=settings.cache_dir, enabled=True, recent_turns_limit=settings.recent_turns_limit)
        app = ChatApplicationService(settings=settings, memory_service=memory)
        for case in _cases():
            record = _record(files, case["file"])
            conv = app.create_conversation(case["id"])
            if record and record.get("id"):
                app.set_active_file(conv.id, str(record["id"]))
            turn_results = []
            for turn in case["turns"]:
                response = app.process_message(conv.id, turn["m"], debug=True)
                checks = _score(response, turn.get("expect", {}))
                turn_passed = all(checks.values()) if checks else True
                entry = {
                    "message": turn["m"],
                    "response_type": response.response_type,
                    "execution_mode": (response.metadata or {}).get("execution_mode"),
                    "checks": checks,
                    "passed": turn_passed,
                }
                turn_results.append(entry)
                if "requirements" in turn:
                    fulfilled = _coverage(turn["requirements"], response, turn.get("expect", {}))
                    missing = [r for r in turn["requirements"] if r not in fulfilled]
                    multipart.append({
                        "id": case["id"], "message": turn["m"],
                        "requested": turn["requirements"], "fulfilled": fulfilled, "missing": missing,
                        "complete": not missing,
                    })
            results.append({"id": case["id"], "category": case["category"], "passed": all(t["passed"] for t in turn_results), "turns": turn_results})

    by_category: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_category.setdefault(item["category"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += int(item["passed"])
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
        "by_category": by_category,
        "multipart_total": len(multipart),
        "multipart_complete": sum(1 for item in multipart if item["complete"]),
        "missing_requirement_count": sum(len(item["missing"]) for item in multipart),
        "generic_clarification_count": sum(
            1 for item in results for turn in item["turns"]
            if turn["response_type"] == "clarification" and turn["checks"].get("no_unwanted_clarification") is False
        ),
    }
    (ARTIFACTS / "answer_quality_results.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "multipart_intent_results.json").write_text(json.dumps({"summary": {"total": len(multipart), "complete": summary["multipart_complete"], "missing_requirement_count": summary["missing_requirement_count"]}, "cases": multipart}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return summary


def _coverage(requirements: list[str], response: Any, expect: dict[str, Any]) -> list[str]:
    table_text = _table_text(response)
    summary = _ascii(response.summary or "")
    md = response.metadata or {}
    fulfilled = []
    rows = len(response.table.rows) if response.table else 0
    for req in requirements:
        if req == "top_n" and 0 < rows <= (expect.get("limit") or 5):
            fulfilled.append(req)
        elif req == "group_count" and (expect.get("dimension", "") in table_text):
            fulfilled.append(req)
        elif req == "percentage" and ("%" in table_text or "%" in summary):
            fulfilled.append(req)
        elif req == "table" and bool(response.table and response.table.rows):
            fulfilled.append(req)
        elif req == "commentary" and (bool(md.get("commentary_attached")) or "nhan xet" in summary):
            fulfilled.append(req)
        elif req == "time_filter" and "413,57" not in (response.summary or ""):
            fulfilled.append(req)
    return fulfilled


if __name__ == "__main__":
    run()
