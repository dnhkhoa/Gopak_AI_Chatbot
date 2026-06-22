from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QUESTIONS_PATH = ROOT / "evaluation" / "customer_questions.json"

from src.application import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService

METADATA_INTENTS = {
    "DATA_OVERVIEW",
    "TABLE_OVERVIEW",
    "SCHEMA_INSPECTION",
    "SAMPLE_ROWS",
    "DATA_RANGE",
    "DATA_QUALITY",
}
NON_SQL_INTENTS = METADATA_INTENTS | {"CLARIFICATION", "REFUSAL", "SAFE_FAILURE"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["development", "holdout", "all"], default="all")
    args = parser.parse_args()

    cases = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    target_cases = [case for case in cases if args.set == "all" or case["set"] == args.set]
    results = run_cases(cases, target_cases)
    write_artifacts(results, args.set)


def run_cases(all_cases: list[dict[str, Any]], target_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = get_settings()
    memory = ConversationMemoryService(
        db_path=ROOT / "data" / "customer_eval_memory.db",
        cache_root=settings.cache_dir,
        enabled=True,
        recent_turns_limit=settings.recent_turns_limit,
    )
    service = ChatApplicationService(settings=settings, memory_service=memory)
    conversations: dict[str, str] = {}
    processed: set[str] = set()
    scored_ids = {case["id"] for case in target_cases}
    results: list[dict[str, Any]] = []

    by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in all_cases:
        if case.get("conversation_id"):
            by_chain[str(case["conversation_id"])].append(case)

    for case in target_cases:
        history = _required_history(case, by_chain)
        for history_case in history:
            if history_case["id"] not in processed:
                _process_case(service, conversations, history_case, score=False)
                processed.add(history_case["id"])
        result = _process_case(service, conversations, case, score=True)
        processed.add(case["id"])
        if result and case["id"] in scored_ids:
            results.append(result)
    return results


def _required_history(case: dict[str, Any], by_chain: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    chain_id = case.get("conversation_id")
    if not chain_id or int(case.get("turn") or 1) <= 1:
        return []
    return [
        item
        for item in sorted(by_chain[str(chain_id)], key=lambda row: int(row.get("turn") or 1))
        if int(item.get("turn") or 1) < int(case.get("turn") or 1)
    ]


def _process_case(
    service: ChatApplicationService,
    conversations: dict[str, str],
    case: dict[str, Any],
    score: bool,
) -> dict[str, Any] | None:
    conversation_key = str(case.get("conversation_id") or case["id"])
    if conversation_key not in conversations:
        conversations[conversation_key] = service.create_conversation(title=case["id"]).id

    started = perf_counter()
    response = service.process_message(conversations[conversation_key], case["question"], debug=True)
    latency_ms = round((perf_counter() - started) * 1000, 1)
    if not score:
        return None

    metadata = response.metadata or {}
    debug = metadata.get("debug") or {}
    actual_intent = _actual_intent(response.response_type, metadata, response.downloads)
    generated_sql = metadata.get("generated_sql") or debug.get("sql")
    query_plan = debug.get("query_plan")
    router_confidence = metadata.get("router_confidence") or metadata.get("deterministic_confidence") or metadata.get("confidence")
    passed, failure_type, manual_review, notes = _judge(case, response, actual_intent, generated_sql, query_plan)
    return {
        "id": case["id"],
        "set": case["set"],
        "category": case["category"],
        "question": case["question"],
        "expected_intent": case["expected_intent"],
        "actual_intent": actual_intent,
        "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
        "router_confidence": router_confidence,
        "response_type": response.response_type,
        "title": response.title,
        "summary": response.summary,
        "primary_value": response.primary_value,
        "query_plan": query_plan,
        "generated_sql": generated_sql,
        "expected": case.get("expected_behavior"),
        "actual": _actual_summary(response),
        "passed": passed,
        "manual_review": manual_review,
        "failure_type": failure_type,
        "llm_called": bool(metadata.get("llm_called")),
        "latency_ms": latency_ms,
        "notes": notes,
    }


def _actual_intent(response_type: str, metadata: dict[str, Any], downloads: list[Any]) -> str:
    mode = metadata.get("execution_mode")
    if mode in NON_SQL_INTENTS:
        return mode
    if response_type == "data_overview":
        return "DATA_OVERVIEW"
    if response_type == "schema":
        return "SCHEMA_INSPECTION"
    if response_type == "sample_table":
        return "SAMPLE_ROWS"
    if response_type == "data_quality":
        return "DATA_QUALITY"
    if response_type == "clarification":
        return "CLARIFICATION"
    if response_type == "refusal":
        return "REFUSAL"
    if response_type == "chart":
        return "CHART_REQUEST"
    if response_type == "dashboard":
        return "DASHBOARD_REQUEST"
    if response_type == "report":
        return "REPORT_REQUEST"
    if downloads:
        return "EXPORT_REQUEST"
    if response_type in {"scalar", "table", "text"}:
        return "ANALYTICAL_QUERY"
    return "SAFE_FAILURE" if response_type == "error" else "ANALYTICAL_QUERY"


def _judge(
    case: dict[str, Any],
    response: Any,
    actual_intent: str,
    generated_sql: str | None,
    query_plan: dict[str, Any] | None,
) -> tuple[bool, str | None, bool, str]:
    expected = case["expected_intent"]
    no_sql = not generated_sql
    default_downtime = _is_default_downtime_false_positive(case, response, generated_sql)

    if default_downtime:
        return False, "DEFAULT_DOWNTIME_FALSE_POSITIVE", False, "Non-downtime/customer metadata question became total downtime."

    if expected in METADATA_INTENTS:
        equivalent = {expected}
        if expected == "DATA_RANGE":
            equivalent.add("DATA_OVERVIEW")
        passed = actual_intent in equivalent and no_sql
        return passed, None if passed else "METADATA_SQL_OR_WRONG_INTENT", False, "Metadata intent must avoid analytical SQL."

    if expected in {"CLARIFICATION", "REFUSAL"}:
        passed = actual_intent == expected and no_sql
        return passed, None if passed else "SAFETY_OR_CLARIFICATION_MISS", False, "Clarification/refusal should not run SQL."

    if expected == "CONVERSATION_FOLLOWUP":
        allowed = {
            "ANALYTICAL_QUERY",
            "CHART_REQUEST",
            "DASHBOARD_REQUEST",
            "REPORT_REQUEST",
            "EXPORT_REQUEST",
            "SAMPLE_ROWS",
            "CLARIFICATION",
            "REFUSAL",
        }
        passed = actual_intent in allowed and response.response_type != "error"
        return passed, None if passed else "MULTITURN_FAILURE", True, "Stateful behavior requires human review."

    if expected in {"CHART_REQUEST", "DASHBOARD_REQUEST", "REPORT_REQUEST", "EXPORT_REQUEST"}:
        allowed = {expected}
        if expected == "EXPORT_REQUEST":
            allowed.update({"REPORT_REQUEST", "ANALYTICAL_QUERY"})
        if expected == "REPORT_REQUEST":
            allowed.update({"EXPORT_REQUEST"})
        passed = actual_intent in allowed and response.response_type not in {"error", "refusal"}
        return passed, None if passed else "ARTIFACT_INTENT_MISS", response.response_type == "table", "Artifact request should produce the requested view or a compatible artifact."

    if expected == "ANALYTICAL_QUERY":
        passed = response.response_type in {"scalar", "table", "chart", "dashboard", "report", "text"} and response.response_type != "error"
        if passed and query_plan:
            passed = str(query_plan.get("intent") or "") not in {"clarification", "refusal", "safe_failure"}
        return passed, None if passed else "ANALYTICAL_FAILURE", False, "Analytical query should return a safe validated result."

    return False, "UNMAPPED_EXPECTATION", True, "No judging rule."


def _is_default_downtime_false_positive(case: dict[str, Any], response: Any, generated_sql: str | None) -> bool:
    expected = case["expected_intent"]
    if expected == "ANALYTICAL_QUERY" and "downtime" in case["question"].lower():
        return False
    sql = (generated_sql or "").lower()
    text = " ".join(str(value or "") for value in [response.title, response.summary, response.primary_value]).lower()
    return (
        expected in NON_SQL_INTENTS
        and (
            ("sum" in sql and "thoi_luong_seconds" in sql)
            or "1.989" in text
            or ("tổng thời gian downtime" in text and response.response_type == "scalar")
        )
    )


def _actual_summary(response: Any) -> str:
    parts = [response.title, response.primary_value, response.summary]
    if response.table:
        parts.append(f"table_rows={len(response.table.rows)}")
    if response.chart:
        parts.append(f"chart={response.chart.type}")
    if response.downloads:
        parts.append("downloads=" + ",".join(item.filename for item in response.downloads))
    return " | ".join(str(part) for part in parts if part)


def write_artifacts(results: list[dict[str, Any]], set_name: str) -> None:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)

    if set_name in {"development", "all"}:
        dev = [row for row in results if row["set"] == "development"]
        (artifacts / "customer_evaluation_dev.json").write_text(json.dumps(dev, ensure_ascii=False, indent=2), encoding="utf-8")
    if set_name in {"holdout", "all"}:
        holdout = [row for row in results if row["set"] == "holdout"]
        (artifacts / "customer_evaluation_holdout.json").write_text(json.dumps(holdout, ensure_ascii=False, indent=2), encoding="utf-8")
    if set_name not in {"development", "holdout"}:
        (artifacts / "customer_evaluation_all.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        (artifacts / f"customer_evaluation_{set_name}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_confusion_matrix(results, artifacts / "customer_intent_confusion_matrix.csv")
    _write_latency(results, artifacts / "customer_latency.csv")
    false_positives = [row for row in results if row["failure_type"] == "DEFAULT_DOWNTIME_FALSE_POSITIVE"]
    (artifacts / "default_downtime_false_positives.json").write_text(json.dumps(false_positives, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary(results, artifacts / "customer_evaluation_summary.md")
    _write_failures(results, artifacts / "customer_evaluation_failures.md")


def _write_confusion_matrix(results: list[dict[str, Any]], path: Path) -> None:
    expected = sorted({row["expected_intent"] for row in results})
    actual = sorted({row["actual_intent"] for row in results})
    counts = Counter((row["expected_intent"], row["actual_intent"]) for row in results)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["expected_intent", *actual])
        for expected_intent in expected:
            writer.writerow([expected_intent, *[counts[(expected_intent, actual_intent)] for actual_intent in actual]])


def _write_latency(results: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "set", "category", "latency_ms", "passed", "llm_called"])
        writer.writeheader()
        for row in results:
            writer.writerow({key: row[key] for key in writer.fieldnames})


def _write_summary(results: list[dict[str, Any]], path: Path) -> None:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    latencies = sorted(float(row["latency_ms"]) for row in results)
    p50 = median(latencies) if latencies else 0
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0
    false_positives = sum(1 for row in results if row["failure_type"] == "DEFAULT_DOWNTIME_FALSE_POSITIVE")
    llm_calls = sum(1 for row in results if row["llm_called"])

    lines = [
        "# Customer Evaluation Summary",
        "",
        f"Total cases: {total}",
        f"Passed: {passed}/{total} ({_pct(passed, total)})",
        f"Default downtime false positives: {false_positives}",
        f"LLM calls recorded: {llm_calls}",
        f"P50 latency: {p50:.1f} ms",
        f"P95 latency: {p95:.1f} ms",
        "",
        "## By Set",
        "",
        "| Set | Passed | Total | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for set_name in sorted({row["set"] for row in results}):
        subset = [row for row in results if row["set"] == set_name]
        ok = sum(1 for row in subset if row["passed"])
        lines.append(f"| {set_name} | {ok} | {len(subset)} | {_pct(ok, len(subset))} |")

    lines.extend(["", "## By Category", "", "| Category | Passed | Total | Accuracy |", "|---|---:|---:|---:|"])
    for category in sorted({row["category"] for row in results}):
        subset = [row for row in results if row["category"] == category]
        ok = sum(1 for row in subset if row["passed"])
        lines.append(f"| {category} | {ok} | {len(subset)} | {_pct(ok, len(subset))} |")

    failure_counts = Counter(row["failure_type"] for row in results if row["failure_type"])
    lines.extend(["", "## Failure Types", "", "| Failure type | Count |", "|---|---:|"])
    for failure_type, count in failure_counts.most_common():
        lines.append(f"| {failure_type} | {count} |")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_failures(results: list[dict[str, Any]], path: Path) -> None:
    failures = [row for row in results if not row["passed"]]
    lines = ["# Customer Evaluation Failures", "", f"Total failures: {len(failures)}", ""]
    for row in failures[:80]:
        lines.extend(
            [
                f"## {row['id']} - {row['failure_type']}",
                "",
                f"- Set: {row['set']}",
                f"- Category: {row['category']}",
                f"- Question: {row['question']}",
                f"- Expected: {row['expected_intent']}",
                f"- Actual: {row['actual_intent']} / {row['response_type']}",
                f"- SQL: `{row['generated_sql'] or ''}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _pct(value: int, total: int) -> str:
    return "0.0%" if total == 0 else f"{value / total * 100:.1f}%"


if __name__ == "__main__":
    main()
