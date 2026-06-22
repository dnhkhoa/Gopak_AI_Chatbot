from __future__ import annotations

import csv
import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts_ingest import main as ingest
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.conversation.state import ConversationState
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor


FAILURES = {
    "complex": "COMPLEX_DECOMPOSITION_ERROR",
    "multi_metric": "MULTI_METRIC_ERROR",
    "percentage": "PERCENTAGE_ERROR",
    "group_average": "GROUP_AVERAGE_ERROR",
    "window": "WINDOW_RANKING_ERROR",
    "nested": "NESTED_QUERY_ERROR",
    "classification": "STATE_CLASSIFICATION_ERROR",
    "merge": "STATE_MERGE_ERROR",
    "reference": "REFERENCE_RESOLUTION_ERROR",
    "persistence": "PERSISTENCE_ERROR",
    "restore": "SESSION_RESTORE_ERROR",
    "context_leak": "CONTEXT_LEAK_ERROR",
    "validation": "QUERY_VALIDATION_ERROR",
    "sql": "SQL_BUILD_ERROR",
    "comparison": "RESULT_COMPARISON_ERROR",
}


COMPLEX_CASES = [
    {
        "id": "CQ-001",
        "category": "multiple_metrics",
        "question": "Hãy tìm top 5 máy có tổng downtime cao nhất, đồng thời hiển thị số lần dừng và thời lượng trung bình.",
        "expect": {"columns": ["may", "total_duration_seconds", "row_count", "avg_duration_seconds"], "limit": 5, "metrics": 3},
    },
    {
        "id": "CQ-002",
        "category": "multiple_metrics",
        "question": "Top 3 nguyên nhân theo tổng downtime, hiển thị thêm số lần dừng và thời lượng trung bình.",
        "expect": {"columns": ["ten_ton_that", "total_duration_seconds", "row_count", "avg_duration_seconds"], "limit": 3, "metrics": 3},
    },
    {
        "id": "CQ-003",
        "category": "percentage",
        "question": "Xếp hạng nguyên nhân theo tỷ lệ phần trăm số lần dừng.",
        "expect": {"columns": ["ten_ton_that", "row_count", "percentage"], "percentage_sum": True},
    },
    {
        "id": "CQ-004",
        "category": "percentage",
        "question": "Tỷ trọng của từng nhóm tổn thất trên tổng số lần dừng là bao nhiêu?",
        "expect": {"columns": ["nhom_ton_that", "row_count", "percentage"], "percentage_sum": True},
    },
    {
        "id": "CQ-005",
        "category": "above_average",
        "question": "Các máy có tổng downtime cao hơn mức trung bình theo máy.",
        "expect": {"columns": ["may", "total_duration_seconds"], "having": "group_average", "first": {"may": "Máy 11"}},
    },
    {
        "id": "CQ-006",
        "category": "above_average",
        "question": "Chỉ giữ các nhóm tổn thất có tổng downtime cao hơn mức trung bình của các nhóm.",
        "expect": {"columns": ["nhom_ton_that", "total_duration_seconds"], "having": "group_average"},
    },
    {
        "id": "CQ-007",
        "category": "windowed_top_n",
        "question": "Top máy theo từng tháng.",
        "expect": {"columns": ["thoi_gian_bat_dau", "may", "total_duration_seconds", "_rank"], "ranking": True},
    },
    {
        "id": "CQ-008",
        "category": "windowed_top_n",
        "question": "Với mỗi tháng, tìm top 3 máy có tổng downtime cao nhất.",
        "expect": {"columns": ["thoi_gian_bat_dau", "may", "total_duration_seconds", "_rank"], "ranking": True, "max_rank": 3},
    },
    {
        "id": "CQ-009",
        "category": "date_range",
        "question": "Trong tháng gần nhất có trong dữ liệu, tìm top 5 máy theo tổng downtime.",
        "expect": {"columns": ["may", "total_duration_seconds"], "time_filter": True, "limit": 5},
    },
    {
        "id": "CQ-010",
        "category": "long_combined",
        "question": "Trong tháng gần nhất có trong dữ liệu, hãy tìm 5 máy có tổng downtime cao nhất, hiển thị thêm số lần dừng và thời lượng trung bình, sắp xếp giảm dần và vẽ biểu đồ cột.",
        "expect": {"columns": ["may", "total_duration_seconds"], "time_filter": True, "output": "bar"},
    },
    {
        "id": "CQ-011",
        "category": "long_combined",
        "question": "Trong tháng gần nhất, tìm top 5 máy theo tổng downtime, chỉ giữ máy cao hơn mức trung bình, và vẽ biểu đồ cột.",
        "expect": {"columns": ["may", "total_duration_seconds"], "time_filter": True, "having": "group_average", "output": "bar"},
    },
    {
        "id": "CQ-012",
        "category": "semantic_multi",
        "question": "Các nguyên nhân liên quan đến QC, kiểm tra chất lượng, chỉnh màu hoặc duyệt màu.",
        "expect": {"columns": ["ten_ton_that"], "no_empty_required": False},
    },
    {
        "id": "CQ-013",
        "category": "chart",
        "question": "Vẽ biểu đồ tròn tỷ trọng của từng nhóm tổn thất theo số lần dừng.",
        "expect": {"columns": ["nhom_ton_that", "row_count", "percentage"], "output": "pie"},
    },
    {
        "id": "CQ-014",
        "category": "report",
        "question": "Xuất báo cáo top 5 máy theo tổng downtime, kèm số lần dừng và thời lượng trung bình.",
        "expect": {"columns": ["may", "total_duration_seconds"], "output": "report"},
    },
    {
        "id": "CQ-015",
        "category": "dashboard",
        "question": "Tạo dashboard tổng quan có tổng downtime và số lần dừng theo máy.",
        "expect": {"columns": ["may", "total_duration_seconds", "row_count"], "output": "dashboard"},
    },
    {
        "id": "CQ-016",
        "category": "period_comparison",
        "question": "So sánh tháng đầu tiên và tháng gần nhất về tổng downtime, số lần dừng và thời lượng trung bình.",
        "expect": {"columns": ["thoi_gian_bat_dau", "total_duration_seconds"], "time_or_group": True},
    },
    {
        "id": "CQ-017",
        "category": "nested",
        "question": "Xác định máy có downtime cao nhất, sau đó lấy top nguyên nhân của máy đó.",
        "expect": {"columns": ["ten_ton_that", "total_duration_seconds"], "nested": True},
    },
    {
        "id": "CQ-018",
        "category": "clarification",
        "question": "Hãy phân tích hiệu quả tốt nhất.",
        "expect": {"intent": ["clarification", "refusal"]},
    },
    {
        "id": "CQ-019",
        "category": "refusal",
        "question": "Dự báo doanh thu tháng sau từ dữ liệu downtime.",
        "expect": {"intent": ["refusal"]},
    },
    {
        "id": "CQ-020",
        "category": "filter",
        "question": "Top 5 máy trong tháng 12/2025 có các lần dừng trên 1 giờ, hiển thị tổng downtime và số lần dừng.",
        "expect": {"columns": ["may", "total_duration_seconds"], "time_filter": True, "duration_filter": True},
    },
]


MULTITURN_SEQUENCES = [
    [
        ("MT-001", "Máy nào có tổng downtime cao nhất?", "NEW_QUERY"),
        ("MT-002", "Vẽ biểu đồ top 5 máy.", "CHANGE_OUTPUT"),
        ("MT-003", "Chỉ lấy tháng gần nhất.", "CHANGE_TIME"),
        ("MT-004", "Với máy đứng đầu, cho tôi top 3 nguyên nhân.", "REFERENCE_ENTITY"),
        ("MT-005", "Chỉ giữ nguyên nhân có thời lượng trung bình trên 30 phút.", "ADD_FILTER"),
    ],
    [
        ("MT-006", "Top 5 nguyên nhân theo tổng downtime.", "NEW_QUERY"),
        ("MT-007", "Nguyên nhân đứng đầu xuất hiện nhiều nhất trên máy nào?", "REFERENCE_ENTITY"),
        ("MT-008", "Chỉ lấy các lần trên một giờ.", "ADD_FILTER"),
        ("MT-009", "Vẽ biểu đồ theo ngày.", "CHANGE_OUTPUT"),
        ("MT-010", "Xóa toàn bộ bộ lọc.", "RESET_CONTEXT"),
    ],
    [
        ("MT-011", "Tổng downtime theo nhóm tổn thất.", "NEW_QUERY"),
        ("MT-012", "Chỉ giữ các nhóm cao hơn mức trung bình.", "ADD_FILTER"),
        ("MT-013", "Tính tỷ trọng từng nhóm.", "CHANGE_METRIC"),
        ("MT-014", "Vẽ biểu đồ tròn.", "CHANGE_OUTPUT"),
        ("MT-015", "Tổng doanh thu là bao nhiêu?", "NEW_QUERY"),
    ],
]


def df_records(df: pd.DataFrame | None, max_rows: int = 20) -> list[dict]:
    if df is None:
        return []
    rows = []
    for row in df.head(max_rows).to_dict("records"):
        rows.append({key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in row.items()})
    return rows


def run_query(question: str, catalog: dict, settings, state: ConversationState) -> dict[str, Any]:
    start = perf_counter()
    planner_start = perf_counter()
    planned = QueryPlanner(catalog, settings).plan(question, state)
    planner_ms = (perf_counter() - planner_start) * 1000
    result = None
    query_ms = 0.0
    error = None
    if planned.plan.intent not in {"clarification", "refusal", "safe_failure"}:
        try:
            query_start = perf_counter()
            result = SafeQueryExecutor(catalog).execute(planned.plan)
            query_ms = (perf_counter() - query_start) * 1000
            state.update_from_plan(planned.plan, planned.plan.output)
            state.update_from_result(result.dataframe)
        except Exception as exc:
            error = repr(exc)
    return {
        "plan": planned.plan,
        "metadata": planned.metadata or {},
        "result": result,
        "error": error,
        "latency_ms": {
            "planner": planner_ms,
            "query": query_ms,
            "total": (perf_counter() - start) * 1000,
        },
    }


def evaluate_expectation(expect: dict, plan, result, error: str | None) -> tuple[bool, str | None, str]:
    if error:
        return False, FAILURES["sql"], error
    if "intent" in expect:
        passed = plan.intent in expect["intent"]
        return passed, None if passed else FAILURES["complex"], "Intent expectation."
    if plan.intent in {"clarification", "refusal", "safe_failure"}:
        return False, FAILURES["complex"], f"Non-executable plan: {plan.intent}"
    df = result.dataframe if result else pd.DataFrame()
    for column in expect.get("columns", []):
        if column not in df.columns:
            return False, FAILURES["comparison"], f"Missing column {column}."
    if expect.get("metrics") and len(plan.metrics) < int(expect["metrics"]):
        return False, FAILURES["multi_metric"], "Missing requested metrics."
    if expect.get("percentage_sum") and "percentage" in df.columns:
        total = float(df["percentage"].sum())
        if not 99.5 <= total <= 100.5:
            return False, FAILURES["percentage"], f"Percentage sum is {total}."
    if expect.get("having") and not plan.having:
        return False, FAILURES["group_average"], "Missing group-average having."
    if expect.get("ranking") and not plan.ranking:
        return False, FAILURES["window"], "Missing ranking spec."
    if expect.get("max_rank") and "_rank" in df.columns and int(df["_rank"].max()) > int(expect["max_rank"]):
        return False, FAILURES["window"], "Rank exceeds max_rank."
    if expect.get("time_filter") and not any(flt.operator == "date_between" for flt in plan.filters):
        return False, FAILURES["complex"], "Missing time filter."
    if expect.get("duration_filter") and not any(flt.operator.startswith("greater") for flt in plan.filters):
        return False, FAILURES["complex"], "Missing duration filter."
    if expect.get("output") and plan.output != expect["output"] and plan.intent != expect["output"]:
        return False, FAILURES["complex"], "Wrong output."
    first = expect.get("first")
    if first and not df.empty:
        for key, value in first.items():
            if str(df.iloc[0][key]) != str(value):
                return False, FAILURES["comparison"], "First row mismatch."
    return True, None, "Passed expectation checks."


def run_complex(catalog: dict, settings) -> list[dict[str, Any]]:
    rows = []
    for case in COMPLEX_CASES:
        state = ConversationState()
        state_before = state.to_prompt_dict()
        outcome = run_query(case["question"], catalog, settings, state)
        passed, failure, notes = evaluate_expectation(case["expect"], outcome["plan"], outcome["result"], outcome["error"])
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "conversation_id": state.conversation_id,
                "turn": 1,
                "turn_type": outcome["metadata"].get("turn_type"),
                "execution_mode": outcome["metadata"].get("execution_mode"),
                "query_complexity": outcome["plan"].query_complexity,
                "state_before": state_before,
                "state_changes": outcome["metadata"].get("state_changes", {}),
                "state_after": state.to_prompt_dict(),
                "expected_plan": case["expect"],
                "actual_plan": outcome["plan"].model_dump(),
                "expected_result": case["expect"],
                "actual_result": {"records": df_records(outcome["result"].dataframe if outcome["result"] else None)},
                "passed": passed,
                "failure_type": failure,
                "latency_ms": outcome["latency_ms"],
                "notes": notes,
            }
        )
    return rows


def run_multiturn(catalog: dict, settings) -> list[dict[str, Any]]:
    rows = []
    for sequence in MULTITURN_SEQUENCES:
        state = ConversationState()
        for turn_index, (case_id, question, expected_turn_type) in enumerate(sequence, start=1):
            before = state.to_prompt_dict()
            outcome = run_query(question, catalog, settings, state)
            actual_turn_type = outcome["metadata"].get("turn_type")
            passed = actual_turn_type == expected_turn_type
            failure = None if passed else FAILURES["classification"]
            if passed and expected_turn_type == "REFERENCE_ENTITY" and outcome["plan"].intent == "clarification":
                passed = False
                failure = FAILURES["reference"]
            if passed and expected_turn_type in {"CHANGE_TIME", "ADD_FILTER"} and not outcome["plan"].filters:
                passed = False
                failure = FAILURES["merge"]
            rows.append(
                {
                    "id": case_id,
                    "category": expected_turn_type,
                    "question": question,
                    "conversation_id": state.conversation_id,
                    "turn": turn_index,
                    "turn_type": actual_turn_type,
                    "expected_turn_type": expected_turn_type,
                    "execution_mode": outcome["metadata"].get("execution_mode"),
                    "query_complexity": outcome["plan"].query_complexity,
                    "state_before": before,
                    "state_changes": outcome["metadata"].get("state_changes", {}),
                    "state_after": state.to_prompt_dict(),
                    "expected_plan": {"turn_type": expected_turn_type},
                    "actual_plan": outcome["plan"].model_dump(),
                    "expected_result": {},
                    "actual_result": {"records": df_records(outcome["result"].dataframe if outcome["result"] else None)},
                    "passed": passed,
                    "failure_type": failure,
                    "latency_ms": outcome["latency_ms"],
                    "notes": "Automated turn classification/merge/reference check.",
                }
            )
    return rows


def run_persistence_checks() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        service = ConversationMemoryService(root / "memory.db", root / "cache")
        start = perf_counter()
        state = service.create_conversation("Round3")
        load_ms = save_ms = 0.0
        save_start = perf_counter()
        service.save_turn(state, role="user", content="Top 5 máy")
        save_ms += (perf_counter() - save_start) * 1000
        state.active_dimensions = ["may"]
        service.save_state(state)
        restored = ConversationMemoryService(root / "memory.db", root / "cache").load_conversation(state.conversation_id)
        load_ms += (perf_counter() - start) * 1000
        rows.append({"id": "MEM-001", "name": "restore_after_restart", "passed": restored.active_dimensions == ["may"], "failure_type": None, "latency_ms": {"load": load_ms, "save": save_ms}})
        second = service.create_conversation("Second")
        rows.append({"id": "MEM-002", "name": "multiple_conversations", "passed": second.conversation_id != state.conversation_id, "failure_type": None, "latency_ms": {}})
        reset = service.reset_conversation(state.conversation_id)
        rows.append({"id": "MEM-003", "name": "reset_conversation", "passed": reset.active_dimensions == [], "failure_type": None, "latency_ms": {}})
        service.delete_conversation(second.conversation_id)
        rows.append({"id": "MEM-004", "name": "delete_conversation", "passed": all(item["id"] != second.conversation_id for item in service.list_conversations()), "failure_type": None, "latency_ms": {}})
        snapshot = service.snapshot()
    for row in rows:
        if not row["passed"]:
            row["failure_type"] = FAILURES["persistence"]
    return rows, snapshot


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    passed = sum(1 for row in rows if row.get("passed"))
    failed = total - passed
    by_category: dict[str, dict[str, int]] = {}
    for row in rows:
        category = row.get("category") or row.get("name") or "unknown"
        item = by_category.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        item["total"] += 1
        item["passed"] += int(bool(row.get("passed")))
        item["failed"] += int(not row.get("passed"))
    return {"total": total, "passed": passed, "failed": failed, "accuracy": passed / total if total else 0, "by_category": by_category}


def write_outputs(complex_rows: list[dict[str, Any]], multiturn_rows: list[dict[str, Any]], memory_rows: list[dict[str, Any]], snapshot: dict[str, Any]) -> None:
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    (artifacts / "complex_query_evaluation.json").write_text(json.dumps(complex_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (artifacts / "multiturn_evaluation.json").write_text(json.dumps(multiturn_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (artifacts / "multiturn_state_traces_round3.json").write_text(json.dumps(multiturn_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (artifacts / "memory_persistence_tests.json").write_text(json.dumps(memory_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (artifacts / "memory_store_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    failures = [row for row in complex_rows if not row["passed"]]
    lines = ["# Complex Query Failures", ""]
    for row in failures:
        lines += [f"## {row['id']} - {row['failure_type']}", "", f"- Question: {row['question']}", f"- Notes: {row['notes']}", f"- Plan: `{json.dumps(row['actual_plan'], ensure_ascii=False, default=str)[:1200]}`", ""]
    (artifacts / "complex_query_failures.md").write_text("\n".join(lines), encoding="utf-8")
    with (artifacts / "latency_round3.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "kind", "execution_mode", "query_complexity", "planner_ms", "query_ms", "total_ms", "passed", "failure_type"])
        writer.writeheader()
        for kind, rows in [("complex", complex_rows), ("multiturn", multiturn_rows)]:
            for row in rows:
                latency = row.get("latency_ms", {})
                writer.writerow(
                    {
                        "id": row["id"],
                        "kind": kind,
                        "execution_mode": row.get("execution_mode"),
                        "query_complexity": row.get("query_complexity"),
                        "planner_ms": latency.get("planner"),
                        "query_ms": latency.get("query"),
                        "total_ms": latency.get("total"),
                        "passed": row.get("passed"),
                        "failure_type": row.get("failure_type"),
                    }
                )
    complex_summary = summarize(complex_rows)
    multiturn_summary = summarize(multiturn_rows)
    memory_summary = summarize(memory_rows)
    lines = [
        "# Round 3 Evaluation Summary",
        "",
        f"- Complex query pass/fail: {complex_summary['passed']}/{complex_summary['failed']} of {complex_summary['total']} ({complex_summary['accuracy']:.1%})",
        f"- Multi-turn pass/fail: {multiturn_summary['passed']}/{multiturn_summary['failed']} of {multiturn_summary['total']} ({multiturn_summary['accuracy']:.1%})",
        f"- Persistence pass/fail: {memory_summary['passed']}/{memory_summary['failed']} of {memory_summary['total']} ({memory_summary['accuracy']:.1%})",
        "",
        "## Complex By Category",
        "",
        "| Category | Total | Passed | Failed |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, item in sorted(complex_summary["by_category"].items()):
        lines.append(f"| {category} | {item['total']} | {item['passed']} | {item['failed']} |")
    lines += ["", "## Multi-turn By Category", "", "| Category | Total | Passed | Failed |", "| --- | ---: | ---: | ---: |"]
    for category, item in sorted(multiturn_summary["by_category"].items()):
        lines.append(f"| {category} | {item['total']} | {item['passed']} | {item['failed']} |")
    (artifacts / "evaluation_summary_round3.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    settings = replace(get_settings(), enable_heuristic_fallback=False, force_legacy_fallback_mode=False)
    catalog = ingest(force=False)
    complex_rows = run_complex(catalog, settings)
    multiturn_rows = run_multiturn(catalog, settings)
    memory_rows, snapshot = run_persistence_checks()
    write_outputs(complex_rows, multiturn_rows, memory_rows, snapshot)
    print(json.dumps({"complex": summarize(complex_rows), "multiturn": summarize(multiturn_rows), "memory": summarize(memory_rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
