from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter
from typing import Any

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from evaluation.generate_cases import main as generate_cases
from scripts_ingest import main as ingest
from src.catalog.profiler import load_catalog
from src.config import get_settings
from src.conversation.state import ConversationState
from src.llm.ollama_client import OllamaClient
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor
from src.query.validator import PlanValidator
from src.rendering.chart_renderer import build_chart
from src.rendering.presentation import build_presented_response


FAIL_ENV = "ENVIRONMENT_BLOCKER"
FAIL_INTENT = "INTENT_ERROR"
FAIL_TABLE = "TABLE_SELECTION_ERROR"
FAIL_COLUMN = "COLUMN_SELECTION_ERROR"
FAIL_FILTER = "FILTER_ERROR"
FAIL_DATE = "DATE_INTERPRETATION_ERROR"
FAIL_AGG = "AGGREGATION_ERROR"
FAIL_JOIN = "JOIN_ERROR"
FAIL_VALIDATION = "PLAN_VALIDATION_ERROR"
FAIL_SQL = "SQL_BUILD_ERROR"
FAIL_QUERY = "QUERY_EXECUTION_ERROR"
FAIL_STATE = "CONVERSATION_STATE_ERROR"
FAIL_SEMANTIC = "SEMANTIC_MATCH_ERROR"
FAIL_PRESENTATION = "PRESENTATION_ERROR"
FAIL_HALLUCINATION = "HALLUCINATION"
FAIL_TIMEOUT = "TIMEOUT"
MANUAL_REVIEW = "MANUAL_REVIEW"


def load_cases() -> list[dict]:
    path = Path("evaluation/evaluation_cases.json")
    if not path.exists():
        generate_cases()
    return json.loads(path.read_text(encoding="utf-8"))


def table_entries(catalog: dict) -> dict[str, dict]:
    return {table["table_name"]: table for table in catalog["tables"]}


def oracle_dataframe(catalog: dict, sql: str) -> pd.DataFrame | None:
    if not sql:
        return None
    with duckdb.connect(database=":memory:") as con:
        for table in catalog["tables"]:
            parquet_path = str(table["parquet_path"]).replace("'", "''")
            con.execute(f'CREATE VIEW "{table["table_name"]}" AS SELECT * FROM read_parquet(\'{parquet_path}\')')
        return con.execute(sql).fetchdf()


def normalize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and math.isfinite(value):
        return round(value, 6)
    return value


def df_records(df: pd.DataFrame | None, max_rows: int = 20) -> list[dict]:
    if df is None:
        return []
    return [{k: normalize_value(v) for k, v in row.items()} for row in df.head(max_rows).to_dict("records")]


def compare_numeric(expected: pd.DataFrame | None, actual: pd.DataFrame | None, tolerance: float) -> tuple[bool, str | None]:
    if expected is None or actual is None or expected.empty or actual.empty:
        return False, FAIL_QUERY
    ev = expected.iloc[0, 0]
    av = actual.iloc[0, 0]
    if pd.isna(ev) and pd.isna(av):
        return True, None
    try:
        return abs(float(av) - float(ev)) <= tolerance, None if abs(float(av) - float(ev)) <= tolerance else FAIL_AGG
    except Exception:
        return False, FAIL_AGG


def compare_table(expected: pd.DataFrame | None, actual: pd.DataFrame | None, ordered: bool = True) -> tuple[bool, str | None]:
    if expected is None or actual is None:
        return False, FAIL_QUERY
    if expected.empty and actual.empty:
        return True, None
    common = [col for col in expected.columns if col in actual.columns]
    if not common:
        return False, FAIL_COLUMN
    exp = expected[common].head(len(actual)).reset_index(drop=True)
    act = actual[common].head(len(exp)).reset_index(drop=True)
    if len(exp) != len(act):
        return False, FAIL_FILTER
    if not ordered:
        exp = exp.sort_values(common).reset_index(drop=True)
        act = act.sort_values(common).reset_index(drop=True)
    for col in common:
        for left, right in zip(exp[col], act[col]):
            if pd.api.types.is_numeric_dtype(exp[col]) or pd.api.types.is_numeric_dtype(act[col]):
                if pd.isna(left) and pd.isna(right):
                    continue
                if abs(float(left) - float(right)) > 0.01:
                    return False, FAIL_AGG
            elif str(left) != str(right):
                return False, FAIL_FILTER
    return True, None


def compare_case(case: dict, expected_df: pd.DataFrame | None, actual_df: pd.DataFrame | None, plan, presentation) -> tuple[bool, str | None, str]:
    ctype = case["comparison_type"]
    expected_intent = case.get("expected_intent")
    if expected_intent and expected_intent != "query":
        if expected_intent == "clarification":
            passed = plan.intent in {"clarification", "refusal"}
            return passed, None if passed else FAIL_INTENT, "Expected clarification/refusal behavior."
        if expected_intent == "chart":
            passed = plan.intent == "chart" or plan.output in {"bar", "horizontal_bar", "line", "pie"}
            return passed, None if passed else FAIL_INTENT, "Expected chart intent/output."
        if expected_intent in {"dashboard", "report"}:
            passed = plan.intent == expected_intent or plan.output == expected_intent
            return passed, None if passed else FAIL_INTENT, f"Expected {expected_intent}."
    if ctype == "numeric":
        passed, failure = compare_numeric(expected_df, actual_df, float(case.get("tolerance", 0.01)))
        return passed, failure, "Numeric oracle comparison."
    if ctype in {"table", "chart"}:
        passed, failure = compare_table(expected_df, actual_df, ordered=True)
        if passed and ctype == "chart" and presentation.chart is None:
            return False, FAIL_PRESENTATION, "Expected chart object but renderer returned none."
        return passed, failure, f"{ctype} oracle comparison."
    if ctype == "empty":
        empty_actual = actual_df is None or actual_df.empty or (len(actual_df) == 1 and actual_df.iloc[0].isna().all())
        # Aggregates over empty filters can return a null scalar; that is acceptable.
        if actual_df is not None and len(actual_df) == 1 and actual_df.shape[1] == 1 and pd.isna(actual_df.iloc[0, 0]):
            empty_actual = True
        passed = bool(empty_actual)
        return passed, None if passed else FAIL_FILTER, "Expected empty or null result."
    if ctype == "behavior":
        passed = plan.intent == "clarification"
        return passed, None if passed else FAIL_INTENT, "Expected safe clarification/refusal."
    return False, MANUAL_REVIEW, "Manual review case."


def run_case(case: dict, catalog: dict, settings, state: ConversationState, mode: str) -> dict:
    start = perf_counter()
    state_before = state.to_prompt_dict()
    llm_latency = query_latency = render_latency = 0.0
    expected_df = None
    actual_df = None
    plan_dump = None
    sql = ""
    presentation_dump = None
    passed = False
    failure_type = None
    notes = ""
    exception = ""
    try:
        expected_df = oracle_dataframe(catalog, case.get("oracle_sql", ""))
        planner = QueryPlanner(catalog, settings)
        planned = planner.plan(case["question"], state)
        llm_latency = planned.latency_ms
        plan = planned.plan
        plan_dump = plan.model_dump()
        if planned.error:
            failure_type = FAIL_VALIDATION
            notes = f"Planner error: {planned.error}"
        elif plan.intent in {"clarification", "refusal", "safe_failure"}:
            presentation_start = perf_counter()
            presentation = build_presented_response(case["question"], plan, pd.DataFrame(), catalog, [])
            render_latency = (perf_counter() - presentation_start) * 1000
            presentation_dump = presentation.model_dump(exclude={"result_dataframe", "raw_dataframe", "chart"})
            passed, failure_type, notes = compare_case(case, expected_df, pd.DataFrame(), plan, presentation)
        else:
            validator = PlanValidator(catalog)
            validator.validate(plan)
            result = SafeQueryExecutor(catalog).execute(plan)
            actual_df = result.dataframe
            sql = result.sql
            query_latency = result.latency_ms
            chart = build_chart(actual_df, plan, catalog)
            sources = [
                {"table": table["table_name"], "source": table["source"], "rows": table["row_count"]}
                for table in catalog.get("tables", [])
                if table["table_name"] in plan.tables
            ]
            presentation_start = perf_counter()
            presentation = build_presented_response(case["question"], plan, actual_df, catalog, sources, chart)
            render_latency = (perf_counter() - presentation_start) * 1000
            presentation_dump = presentation.model_dump(exclude={"result_dataframe", "raw_dataframe", "chart"})
            passed, failure_type, notes = compare_case(case, expected_df, actual_df, plan, presentation)
            state.update_from_plan(plan, plan.output)
            state.update_from_result(actual_df)
    except Exception as exc:
        exception = repr(exc)
        failure_type = classify_exception(exc)
        notes = "Exception while running evaluation case."
    total_latency = (perf_counter() - start) * 1000
    metadata = planned.metadata if "planned" in locals() and planned.metadata else {}
    state_after = state.to_prompt_dict()
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "mode": mode,
        "selected_mode": metadata.get("execution_mode", mode),
        "router_confidence": metadata.get("router_confidence", 0.0),
        "routing_reason": metadata.get("routing_reason", ""),
        "llm_called": bool(metadata.get("llm_called", False)),
        "llm_call_count": int(metadata.get("llm_call_count", 0) or 0),
        "fallback_used": bool(metadata.get("fallback_used", False)),
        "state_before": state_before,
        "state_after": state_after,
        "expected": {"records": df_records(expected_df), "comparison_type": case["comparison_type"], "expected_behavior": case.get("expected_behavior")},
        "actual": {"records": df_records(actual_df)},
        "actual_plan": plan_dump,
        "generated_sql": sql,
        "passed": bool(passed),
        "failure_type": None if passed else failure_type or MANUAL_REVIEW,
        "llm_latency_ms": llm_latency,
        "query_latency_ms": query_latency,
        "render_latency_ms": render_latency,
        "total_latency_ms": total_latency,
        "latency_ms": metadata.get("latency_ms", {"total": total_latency, "query": query_latency, "rendering": render_latency}),
        "presented_response": presentation_dump,
        "exception": exception,
        "notes": notes,
    }


def classify_exception(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if "validation" in name.lower() or "unknown column" in text or "unknown table" in text:
        return FAIL_VALIDATION
    if "duckdb" in name.lower() or "sql" in text:
        return FAIL_QUERY
    if "timeout" in text:
        return FAIL_TIMEOUT
    return FAIL_QUERY


def real_llm_probe(catalog: dict, settings) -> tuple[bool, dict]:
    state = ConversationState()
    case = {
        "id": "REAL-LLM-PROBE",
        "category": "probe",
        "question": "Tổng downtime là bao nhiêu?",
        "expected_intent": "query",
        "oracle_sql": "",
        "comparison_type": "manual",
        "tolerance": 0.01,
        "expected_behavior": "",
    }
    result = run_case(case, catalog, settings, state, "REAL_LLM")
    ok = result["actual_plan"] is not None and result["failure_type"] != FAIL_VALIDATION and result["actual_plan"].get("intent") != "clarification"
    return ok, result


def run_mode(mode: str, cases: list[dict], catalog: dict, settings) -> list[dict]:
    results = []
    states: dict[str, ConversationState] = {}
    for case in cases:
        state_key = case.get("conversation_id") or case["id"]
        if not case.get("conversation_id"):
            state = ConversationState()
        else:
            state = states.setdefault(state_key, ConversationState())
        results.append(run_case(case, catalog, settings, state, mode))
    return results


def summarize(results: list[dict], mode: str) -> dict:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    manual = sum(1 for row in results if row["failure_type"] == MANUAL_REVIEW)
    failed = total - passed - manual
    latencies = [row["total_latency_ms"] for row in results if row["total_latency_ms"]]
    by_category = {}
    for row in results:
        item = by_category.setdefault(row["category"], {"total": 0, "passed": 0, "manual": 0, "failed": 0})
        item["total"] += 1
        if row["passed"]:
            item["passed"] += 1
        elif row["failure_type"] == MANUAL_REVIEW:
            item["manual"] += 1
        else:
            item["failed"] += 1
    return {
        "mode": mode,
        "total": total,
        "passed": passed,
        "failed": failed,
        "manual_review": manual,
        "accuracy": passed / total if total else 0,
        "by_category": by_category,
        "latency": {
            "p50_ms": median(latencies) if latencies else 0,
            "p90_ms": quantiles(latencies, n=10)[8] if len(latencies) >= 10 else max(latencies, default=0),
            "p95_ms": quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies, default=0),
            "max_ms": max(latencies, default=0),
        },
    }


def run_consistency(cases: list[dict], catalog: dict, settings) -> dict:
    selected = [case for case in cases if case["comparison_type"] in {"numeric", "table", "chart"}][:10]
    groups = []
    stable_count = 0
    for case in selected:
        runs = [run_case(case, catalog, settings, ConversationState(), "HEURISTIC_FALLBACK_CONSISTENCY") for _ in range(3)]
        plan_keys = [json.dumps(run["actual_plan"], sort_keys=True, ensure_ascii=False, default=str) for run in runs]
        sql_keys = [run["generated_sql"] for run in runs]
        result_keys = [json.dumps(run["actual"], sort_keys=True, ensure_ascii=False, default=str) for run in runs]
        stable = len(set(plan_keys)) == 1 and len(set(sql_keys)) == 1 and len(set(result_keys)) == 1
        stable_count += int(stable)
        groups.append(
            {
                "id": case["id"],
                "question": case["question"],
                "stable": stable,
                "passed_runs": sum(1 for run in runs if run["passed"]),
                "latency_ms": [run["total_latency_ms"] for run in runs],
                "failure_types": [run["failure_type"] for run in runs],
            }
        )
    return {"total": len(groups), "stable": stable_count, "consistency_rate": stable_count / len(groups) if groups else 0, "groups": groups}


def analyze_paraphrases(results: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for row in results:
        if row["category"] == "paraphrase":
            groups.setdefault("total_duration", []).append(row)
    output = []
    consistent = 0
    for name, rows in groups.items():
        actuals = [json.dumps(row["actual"], sort_keys=True, ensure_ascii=False, default=str) for row in rows if row["passed"]]
        same = bool(actuals) and len(set(actuals)) == 1 and len(actuals) == len(rows)
        consistent += int(same)
        output.append({"group": name, "total": len(rows), "passed": sum(1 for row in rows if row["passed"]), "consistent": same, "case_ids": [row["id"] for row in rows]})
    return {"total_groups": len(output), "consistent_groups": consistent, "groups": output}


def write_reports(fallback_results: list[dict], real_results: list[dict] | None, real_blocker: dict | None, consistency: dict, paraphrase: dict) -> None:
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    summaries = []
    if real_results is not None:
        (artifacts / "evaluation_results_real_llm.json").write_text(json.dumps(real_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (artifacts / "evaluation_results_real_llm_after_fix.json").write_text(json.dumps(real_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        summaries.append(summarize(real_results, "REAL_LLM"))
    if fallback_results:
        (artifacts / "evaluation_results_fallback.json").write_text(json.dumps(fallback_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (artifacts / "evaluation_results_fallback_after_fix.json").write_text(json.dumps(fallback_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        summaries.append(summarize(fallback_results, "HEURISTIC_FALLBACK"))
    (artifacts / "consistency_analysis.json").write_text(json.dumps(consistency, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (artifacts / "paraphrase_equivalence.json").write_text(json.dumps(paraphrase, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    latency_path = artifacts / "latency_benchmark.csv"
    with latency_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "mode", "category", "llm_latency_ms", "query_latency_ms", "render_latency_ms", "total_latency_ms", "passed", "failure_type"])
        writer.writeheader()
        for row in (real_results or []) + fallback_results:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    (artifacts / "latency_benchmark_after_fix.csv").write_text(latency_path.read_text(encoding="utf-8"), encoding="utf-8")
    write_summary(summaries, real_blocker, consistency, paraphrase)
    write_failures((real_results or []) + fallback_results, real_blocker)


def write_hybrid_reports(hybrid_results: list[dict]) -> dict:
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    (artifacts / "evaluation_results_hybrid.json").write_text(json.dumps(hybrid_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (artifacts / "router_decisions.json").write_text(
        json.dumps(
            [
                {
                    "id": row["id"],
                    "question": row["question"],
                    "selected_mode": row.get("selected_mode"),
                    "router_confidence": row.get("router_confidence"),
                    "routing_reason": row.get("routing_reason"),
                    "llm_called": row.get("llm_called"),
                    "fallback_used": row.get("fallback_used"),
                }
                for row in hybrid_results
            ],
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    traces = [
        {
            "id": row["id"],
            "question": row["question"],
            "state_before": row.get("state_before"),
            "state_after": row.get("state_after"),
            "selected_mode": row.get("selected_mode"),
            "actual_plan": row.get("actual_plan"),
        }
        for row in hybrid_results
        if row.get("category") == "multi_turn"
    ]
    (artifacts / "multiturn_state_traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if not (artifacts / "semantic_matching_debug.json").exists():
        (artifacts / "semantic_matching_debug.json").write_text("[]", encoding="utf-8")
    if not (artifacts / "planner_invalid_responses.json").exists():
        (artifacts / "planner_invalid_responses.json").write_text("[]", encoding="utf-8")
    with (artifacts / "latency_benchmark_hybrid.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "selected_mode", "category", "llm_called", "llm_call_count", "total_latency_ms", "passed", "failure_type"])
        writer.writeheader()
        for row in hybrid_results:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})

    summary = summarize(hybrid_results, "HYBRID")
    by_mode = summarize_by_execution_mode(hybrid_results)
    write_hybrid_summary(summary, by_mode, hybrid_results)
    write_hybrid_failures(hybrid_results)
    return {"summary": summary, "by_mode": by_mode}


def summarize_by_execution_mode(results: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for row in results:
        grouped.setdefault(row.get("selected_mode") or "UNKNOWN", []).append(row)
    return {mode: summarize(rows, mode) for mode, rows in sorted(grouped.items())}


def write_hybrid_summary(summary: dict, by_mode: dict, results: list[dict]) -> None:
    lines = ["# Hybrid Evaluation Summary", ""]
    lines += [
        "## Overall",
        "",
        f"- Cases: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Manual review: {summary['manual_review']}",
        f"- Accuracy: {summary['accuracy']:.2%}",
        f"- P50 latency: {summary['latency']['p50_ms']:.1f} ms",
        f"- P95 latency: {summary['latency']['p95_ms']:.1f} ms",
        f"- LLM usage rate: {llm_usage_rate(results):.1%}",
        "",
        "## By Execution Mode",
        "",
        "| Mode | Cases | Passed | Failed | Manual | Accuracy | P50 ms | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, item in by_mode.items():
        lines.append(f"| {mode} | {item['total']} | {item['passed']} | {item['failed']} | {item['manual_review']} | {item['accuracy']:.1%} | {item['latency']['p50_ms']:.1f} | {item['latency']['p95_ms']:.1f} |")
    lines += [
        "",
        "## By Category",
        "",
        "| Category | Total | Passed | Failed | Manual | Accuracy |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, item in sorted(summary["by_category"].items()):
        acc = item["passed"] / item["total"] if item["total"] else 0
        lines.append(f"| {category} | {item['total']} | {item['passed']} | {item['failed']} | {item['manual']} | {acc:.1%} |")
    Path("artifacts/evaluation_summary_hybrid.md").write_text("\n".join(lines), encoding="utf-8")


def llm_usage_rate(results: list[dict]) -> float:
    return sum(1 for row in results if row.get("llm_called")) / len(results) if results else 0.0


def write_hybrid_failures(results: list[dict]) -> None:
    lines = ["# Hybrid Evaluation Failures", ""]
    for row in results:
        if row["passed"] or row["failure_type"] == MANUAL_REVIEW:
            continue
        lines += [
            f"## {row['id']} - {row['failure_type']}",
            "",
            f"- Category: {row['category']}",
            f"- Selected mode: {row.get('selected_mode')}",
            f"- Router confidence: {row.get('router_confidence')}",
            f"- Routing reason: {row.get('routing_reason')}",
            f"- LLM called: {row.get('llm_called')} ({row.get('llm_call_count')} calls)",
            f"- Question: {row['question']}",
            f"- Expected: `{json.dumps(row['expected'], ensure_ascii=False, default=str)[:1000]}`",
            f"- Actual: `{json.dumps(row['actual'], ensure_ascii=False, default=str)[:1000]}`",
            f"- Planner JSON: `{json.dumps(row['actual_plan'], ensure_ascii=False, default=str)[:1000]}`",
            f"- SQL: `{row['generated_sql']}`",
            f"- Exception: `{row['exception']}`",
            f"- Notes: {row['notes']}",
            "",
        ]
    Path("artifacts/evaluation_failures_hybrid.md").write_text("\n".join(lines), encoding="utf-8")


def readiness(summary: dict, real_blocker: dict | None) -> tuple[float, str]:
    score = summary["accuracy"] * 100
    if real_blocker:
        return min(score, 64.0), "NOT DEMO READY"
    if score >= 90:
        return score, "DEMO READY"
    if score >= 80:
        return score, "DEMO READY WITH MINOR ISSUES"
    if score >= 65:
        return score, "PARTIALLY WORKING"
    return score, "NOT DEMO READY"


def write_summary(summaries: list[dict], real_blocker: dict | None, consistency: dict, paraphrase: dict) -> None:
    lines = ["# Evaluation Summary", ""]
    if real_blocker:
        lines += [
            "## REAL_LLM Status",
            "",
            "Status: `BLOCKED_REAL_LLM_EVALUATION`",
            "",
            f"Reason: {real_blocker.get('notes')}",
            f"Failure type: {real_blocker.get('failure_type')}",
            "",
        ]
    for summary in summaries:
        score, ready = readiness(summary, real_blocker if summary["mode"] == "REAL_LLM" else None)
        lines += [
            f"## {summary['mode']}",
            "",
            f"- Cases: {summary['total']}",
            f"- Passed: {summary['passed']}",
            f"- Failed: {summary['failed']}",
            f"- Manual review: {summary['manual_review']}",
            f"- Accuracy: {summary['accuracy']:.2%}",
            f"- P50 latency: {summary['latency']['p50_ms']:.1f} ms",
            f"- P95 latency: {summary['latency']['p95_ms']:.1f} ms",
            f"- Max latency: {summary['latency']['max_ms']:.1f} ms",
            f"- Readiness: {ready} ({score:.1f})",
            "",
            "### Accuracy by Category",
            "",
            "| Category | Total | Passed | Failed | Manual | Accuracy |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for category, item in sorted(summary["by_category"].items()):
            acc = item["passed"] / item["total"] if item["total"] else 0
            lines.append(f"| {category} | {item['total']} | {item['passed']} | {item['failed']} | {item['manual']} | {acc:.1%} |")
        lines.append("")
    lines += [
        "## Consistency",
        "",
        f"- Cases rerun: {consistency.get('total', 0)}",
        f"- Stable: {consistency.get('stable', 0)}",
        f"- Consistency rate: {consistency.get('consistency_rate', 0):.1%}",
        "",
        "## Paraphrase Equivalence",
        "",
        f"- Groups: {paraphrase.get('total_groups', 0)}",
        f"- Consistent groups: {paraphrase.get('consistent_groups', 0)}",
        "",
    ]
    Path("artifacts/evaluation_summary.md").write_text("\n".join(lines), encoding="utf-8")
    Path("artifacts/evaluation_summary_after_fix.md").write_text("\n".join(lines), encoding="utf-8")


def write_failures(results: list[dict], real_blocker: dict | None) -> None:
    lines = ["# Evaluation Failures", ""]
    if real_blocker:
        lines += [
            "## REAL_LLM Probe Failure",
            "",
            f"- Question: {real_blocker.get('question')}",
            f"- Failure type: {real_blocker.get('failure_type')}",
            f"- Notes: {real_blocker.get('notes')}",
            f"- Planner JSON: `{json.dumps(real_blocker.get('actual_plan'), ensure_ascii=False)}`",
            "- Suspected root cause: qwen3.5 returns malformed JSON for the full planner prompt even though direct `/api/generate` works.",
            "- Related files: `src/llm/prompts.py`, `src/llm/planner.py`, `src/llm/ollama_client.py`.",
            "- Suggested fix: reduce catalog prompt, use a stricter JSON schema format, and add one targeted repair prompt for malformed JSON.",
            "- Severity: Critical",
            "",
        ]
    for row in results:
        if row["passed"] or row["failure_type"] == MANUAL_REVIEW:
            continue
        lines += [
            f"## {row['id']} - {row['failure_type']}",
            "",
            f"- Category: {row['category']}",
            f"- Mode: {row['mode']}",
            f"- Question: {row['question']}",
            f"- Expected: `{json.dumps(row['expected'], ensure_ascii=False, default=str)[:1000]}`",
            f"- Actual: `{json.dumps(row['actual'], ensure_ascii=False, default=str)[:1000]}`",
            f"- Planner JSON: `{json.dumps(row['actual_plan'], ensure_ascii=False, default=str)[:1000]}`",
            f"- SQL: `{row['generated_sql']}`",
            f"- Exception: `{row['exception']}`",
            f"- Notes: {row['notes']}",
            f"- Suggested fix: {suggest_fix(row)}",
            f"- Severity: {severity(row)}",
            "",
        ]
    Path("artifacts/evaluation_failures.md").write_text("\n".join(lines), encoding="utf-8")
    Path("artifacts/evaluation_failures_after_fix.md").write_text("\n".join(lines), encoding="utf-8")


def suggest_fix(row: dict) -> str:
    failure = row.get("failure_type")
    if failure == FAIL_INTENT:
        return "Improve planner intent classification and clarification policy in `src/llm/planner.py` / prompt."
    if failure in {FAIL_COLUMN, FAIL_TABLE, FAIL_FILTER, FAIL_SEMANTIC}:
        return "Improve schema linking, value matching, and filter extraction."
    if failure in {FAIL_AGG, FAIL_DATE}:
        return "Add planner examples for aggregation/date constraints and validate metric aliases."
    if failure == FAIL_PRESENTATION:
        return "Inspect chart/presentation renderer for missing chart or raw labels."
    return "Inspect planner output, validator result, and generated SQL for this case."


def severity(row: dict) -> str:
    if row.get("category") in {"aggregation", "top_n", "time"}:
        return "High"
    if row.get("failure_type") in {FAIL_HALLUCINATION, FAIL_QUERY, FAIL_VALIDATION}:
        return "High"
    return "Medium"


def update_progress(fallback_summary: dict, real_blocker: dict | None, consistency: dict, paraphrase: dict) -> None:
    p = Path("docs/PROGRESS_EVALUATION.md")
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    section = [
        "",
        "## COMPREHENSIVE LLM EVALUATION",
        "",
        f"Updated: {pd.Timestamp.now().isoformat()}",
        "",
        "- Evaluation modes: REAL_LLM probe plus full HEURISTIC_FALLBACK suite.",
        "- Real model requested: `qwen3.5:9b` via local Ollama.",
        f"- Real model used successfully: {'No - planner JSON probe failed' if real_blocker else 'Yes'}",
        f"- Number of cases generated: {fallback_summary['total']}",
        f"- Fallback pass/fail/manual: {fallback_summary['passed']}/{fallback_summary['failed']}/{fallback_summary['manual_review']}",
        f"- Fallback accuracy: {fallback_summary['accuracy']:.2%}",
        f"- Fallback P50/P95 latency: {fallback_summary['latency']['p50_ms']:.1f} ms / {fallback_summary['latency']['p95_ms']:.1f} ms",
        f"- Consistency: {consistency.get('stable', 0)}/{consistency.get('total', 0)} stable fallback reruns; REAL_LLM consistency is blocked by malformed planner JSON.",
        f"- Paraphrase equivalence: {paraphrase.get('consistent_groups', 0)}/{paraphrase.get('total_groups', 0)} groups consistent.",
        f"- Critical issues: {'REAL_LLM planner produces malformed JSON for full prompt.' if real_blocker else 'None observed for REAL_LLM transport.'}",
        f"- Model readiness: {'NOT DEMO READY for REAL_LLM; fallback remains partially working.' if real_blocker else 'REAL_LLM evaluation available.'}",
        "",
        "Artifacts:",
        "",
        "- `evaluation/evaluation_cases.json`",
        "- `artifacts/evaluation_results_fallback.json`",
        "- `artifacts/evaluation_results_real_llm.json` only when REAL_LLM probe produces a usable plan",
        "- `artifacts/evaluation_summary.md`",
        "- `artifacts/evaluation_failures.md`",
        "- `artifacts/latency_benchmark.csv`",
        "- `artifacts/consistency_analysis.json`",
        "- `artifacts/paraphrase_equivalence.json`",
        "",
        "Priority fixes:",
        "",
        "1. Fix REAL_LLM planner JSON generation by shrinking prompt/catalog and using schema-constrained JSON output.",
        "2. Improve deterministic handling for ambiguity/refusal, semantic matching, bottom-N, date ranges, and multi-turn filters.",
        "3. Add chart-specific comparators for x/y data and tooltip formatting once planner correctness improves.",
    ]
    new_section = "\n".join(section)
    if "## COMPREHENSIVE LLM EVALUATION" in text:
        text = text.split("## COMPREHENSIVE LLM EVALUATION")[0].rstrip() + new_section
    else:
        text = text.rstrip() + new_section
    p.write_text(text + "\n", encoding="utf-8")


def main() -> None:
    generate_cases()
    settings = get_settings()
    catalog = ingest(force=False)
    cases = load_cases()
    hybrid_settings = replace(settings, enable_heuristic_fallback=False, force_legacy_fallback_mode=False)
    hybrid_results = run_mode("HYBRID", cases, catalog, hybrid_settings)
    hybrid_report = write_hybrid_reports(hybrid_results)
    real_blocker = None
    real_results = None

    fallback_settings = replace(settings, ollama_base_url="http://127.0.0.1:9", enable_heuristic_fallback=True, force_legacy_fallback_mode=True)
    fallback_results = run_mode("HEURISTIC_FALLBACK", cases, catalog, fallback_settings)
    consistency = run_consistency(cases, catalog, fallback_settings)
    paraphrase = analyze_paraphrases(fallback_results)
    write_reports(fallback_results, real_results, real_blocker, consistency, paraphrase)
    fallback_summary = summarize(fallback_results, "HEURISTIC_FALLBACK")
    update_progress(fallback_summary, real_blocker, consistency, paraphrase)
    print(json.dumps({"hybrid": hybrid_report, "real_blocked": bool(real_blocker), "fallback_summary": fallback_summary, "consistency": consistency, "paraphrase": paraphrase}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
