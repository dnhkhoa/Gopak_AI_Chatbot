from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.catalog.profiler import load_catalog
from src.config import get_settings
from src.conversation.state import ConversationState
from src.llm.planner import QueryPlanner
from src.query.validator import PlanValidator


PROBES = [
    "Tổng downtime là bao nhiêu?",
    "Tổng số bản ghi downtime là bao nhiêu?",
    "Thời gian downtime trung bình?",
    "Downtime lớn nhất là bao nhiêu?",
    "Có bao nhiêu máy khác nhau?",
    "Top 5 máy theo tổng downtime.",
    "Top 10 nguyên nhân theo số lần xuất hiện.",
    "Máy có downtime trung bình cao nhất.",
    "Downtime theo ngày.",
    "Tổng downtime tháng 12/2025.",
    "Máy 29 downtime tháng 12/2025 bao lâu?",
    "Các lần dừng trên 30 phút.",
    "Tổng downtime của Máy 11 và Máy 29.",
    "Vẽ biểu đồ downtime theo ngày.",
    "Tạo dashboard tổng quan.",
    "Tạo báo cáo HTML downtime.",
    "Máy nào tốt nhất?",
    "Doanh thu năm 2024 là bao nhiêu?",
    "So sánh downtime với loss assignment theo từng dòng.",
    "Dữ liệu của máy KHÔNG_TỒN_TẠI là gì?",
]


def main() -> None:
    settings = get_settings()
    settings = settings.__class__(**{**settings.__dict__, "enable_heuristic_fallback": False})
    catalog = load_catalog(settings.cache_dir)
    validator = PlanValidator(catalog)
    rows = []
    for question in PROBES:
        for run in range(1, 4):
            started = perf_counter()
            planner = QueryPlanner(catalog, settings)
            result = planner.plan(question, ConversationState())
            parseable = result.error is None
            valid = False
            validation_error = None
            try:
                if result.error:
                    raise ValueError(result.error)
                if result.plan.intent not in {"clarification", "refusal"}:
                    validator.validate(result.plan)
                valid = True
            except Exception as exc:
                validation_error = str(exc)
            rows.append(
                {
                    "question": question,
                    "run": run,
                    "parseable": parseable,
                    "valid_plan": valid,
                    "intent": result.plan.intent,
                    "plan": result.plan.model_dump(),
                    "raw_response": result.raw_response,
                    "used_fallback": result.used_fallback,
                    "metadata": result.metadata,
                    "error": result.error,
                    "validation_error": validation_error,
                    "latency_ms": (perf_counter() - started) * 1000,
                }
            )
    summary = {
        "total_runs": len(rows),
        "parseable": sum(1 for row in rows if row["parseable"]),
        "valid_plans": sum(1 for row in rows if row["valid_plan"]),
        "json_validity_rate": sum(1 for row in rows if row["parseable"]) / len(rows),
        "valid_plan_rate": sum(1 for row in rows if row["valid_plan"]) / len(rows),
    }
    output = {"summary": summary, "rows": rows}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/planner_probe_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    invalid = [
        {
            "question": row["question"],
            "raw_response": row["raw_response"],
            "prompt_length": None,
            "output_tokens": len(str(row["raw_response"]).split()),
            "finish_reason": None,
            "pydantic_error": row["validation_error"] or row["error"],
            "retry_result": (row.get("metadata") or {}).get("retry"),
            "metadata": row.get("metadata"),
        }
        for row in rows
        if not row["parseable"] or not row["valid_plan"]
    ]
    Path("artifacts/planner_invalid_responses.json").write_text(json.dumps(invalid, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
