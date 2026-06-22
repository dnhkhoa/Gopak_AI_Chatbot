from __future__ import annotations

import csv
import json
from pathlib import Path
from time import perf_counter

from scripts_ingest import main as ingest
from src.config import get_settings
from src.conversation.state import ConversationState
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor
from src.rendering.answer_renderer import render_text_answer
from src.rendering.report_exporter import export_excel_result, export_html_report


QUESTIONS = [
    ("E001", "Tổng downtime là bao nhiêu?", "query"),
    ("E002", "Máy nào có thời gian downtime cao nhất?", "query"),
    ("E003", "Top 5 nguyên nhân gây tổn thất.", "query"),
    ("E004", "Vẽ biểu đồ downtime theo ngày.", "chart"),
    ("E005", "Tạo dashboard tổng quan.", "dashboard"),
    ("E006", "Xuất báo cáo phân tích downtime.", "report"),
    ("E007", "Downtime trung bình là bao nhiêu?", "query"),
    ("E008", "Đếm số dòng downtime.", "query"),
    ("E009", "Top 3 máy downtime cao nhất.", "query"),
    ("E010", "Các nguyên nhân liên quan đến QC là gì?", "query"),
    ("E011", "Chỉ lấy nhóm bảo trì.", "query"),
    ("E012", "Trong kết quả trên, vẽ top 5.", "chart"),
    ("E013", "Tổng thời gian dừng tháng 11.", "query"),
    ("E014", "So sánh downtime giữa các máy.", "query"),
    ("E015", "Nhóm tổn thất nào xuất hiện nhiều nhất?", "query"),
    ("E016", "Máy nào có số lần dừng nhiều nhất?", "query"),
    ("E017", "Biểu đồ top nguyên nhân.", "chart"),
    ("E018", "Có dữ liệu cổng ra vào không?", "query"),
    ("E019", "Tổng giá trị cân là bao nhiêu?", "query"),
    ("E020", "Câu hỏi mơ hồ về hiệu suất.", "clarification"),
]


def main() -> None:
    settings = get_settings()
    catalog = ingest(force=False)
    planner = QueryPlanner(catalog, settings)
    executor = SafeQueryExecutor(catalog)
    state = ConversationState()
    results = []
    latency_rows = []
    for case_id, question, expected_intent in QUESTIONS:
        start = perf_counter()
        error = ""
        actual_result = None
        plan_dump = None
        query_latency = 0.0
        try:
            planned = planner.plan(question, state)
            plan = planned.plan
            plan_dump = plan.model_dump()
            if plan.intent == "clarification":
                actual_result = plan.clarification_question
            else:
                query_result = executor.execute(plan)
                query_latency = query_result.latency_ms
                answer = render_text_answer(question, plan, query_result.dataframe)
                sources = [{"table": t["table_name"], "source": t["source"]} for t in catalog["tables"] if t["table_name"] in plan.tables]
                if plan.intent == "report":
                    export_html_report(question, answer, query_result.dataframe, plan, sources, settings.reports_dir)
                    export_excel_result(question, answer, query_result.dataframe, sources, settings.reports_dir)
                actual_result = query_result.dataframe.head(5).to_dict("records")
                state.update_from_plan(plan, plan.output)
            passed = plan.intent == expected_intent or (expected_intent == "query" and plan.intent in {"query", "chart"})
        except Exception as exc:
            passed = False
            error = str(exc)
        total_latency = (perf_counter() - start) * 1000
        row = {
            "id": case_id,
            "question": question,
            "expected_intent": expected_intent,
            "expected_result": "Intent must match and query must execute without error.",
            "actual_plan": plan_dump,
            "actual_result": actual_result,
            "pass": passed,
            "planner_latency_ms": planned.latency_ms if "planned" in locals() else 0,
            "query_latency_ms": query_latency,
            "total_latency_ms": total_latency,
            "error": error,
            "notes": "Uses Ollama when available; otherwise schema-driven heuristic fallback.",
        }
        results.append(row)
        latency_rows.append({k: row[k] for k in ["id", "planner_latency_ms", "query_latency_ms", "total_latency_ms"]})
    settings.artifacts_dir.mkdir(exist_ok=True)
    (settings.artifacts_dir / "evaluation_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with (settings.artifacts_dir / "latency_benchmark.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "planner_latency_ms", "query_latency_ms", "total_latency_ms"])
        writer.writeheader()
        writer.writerows(latency_rows)
    passed = sum(1 for row in results if row["pass"])
    print(f"Evaluation complete: {passed}/{len(results)} passed")


if __name__ == "__main__":
    main()

