from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.run_file_scoped_benchmark import _records_by_key, _response_matches, generate_cases
from src.application import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService

ARTIFACTS = ROOT / "artifacts"


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    records = _records_by_key()
    inventory: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []
    histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    active_conversations: dict[str, str] = {}
    previous_active: dict[str, str | None] = {}

    with tempfile.TemporaryDirectory(prefix="gopak-file-scope-audit-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        for case in generate_cases():
            sequence_id = case.get("sequence_id") or case["id"]
            conversation_id = active_conversations.get(sequence_id)
            if not conversation_id:
                conversation_id = app.create_conversation(title=sequence_id).id
                active_conversations[sequence_id] = conversation_id
                previous_active[sequence_id] = None
            expected_file_key = case.get("active_file_key")
            expected_record = records.get(expected_file_key or "") or {}
            expected_file_id = str(expected_record.get("id") or "")
            if expected_file_id:
                app.set_active_file(conversation_id, expected_file_id)
            state_before = memory.load_conversation(conversation_id)
            allowed_catalog = app.get_catalog_for_file(state_before.active_file_id or "")
            allowed_tables = [str(table.get("table_name") or "") for table in allowed_catalog.get("tables", [])]
            response = app.process_message(conversation_id, case["question"], debug=True)
            metadata = response.metadata or {}
            debug = metadata.get("debug") if isinstance(metadata.get("debug"), dict) else {}
            query_plan = debug.get("query_plan") if isinstance(debug, dict) else None
            sql = metadata.get("generated_sql") or (debug or {}).get("sql")
            expected_no_sql = bool(case.get("expected_no_sql"))
            file_ok = not expected_file_id or metadata.get("active_file_id") == expected_file_id
            no_sql_ok = not expected_no_sql or not sql
            type_ok = _response_matches(response.response_type, case["expected_response_type"])
            passed = bool(type_ok and no_sql_ok and file_ok)
            turn_index = len(histories[sequence_id])
            history_before = list(histories[sequence_id])
            result = {
                **case,
                "conversation_id": conversation_id,
                "turn_index": turn_index,
                "actual_response_type": response.response_type,
                "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
                "active_file_id": metadata.get("active_file_id"),
                "active_file_name": metadata.get("active_file_name"),
                "previous_active_file_id": previous_active.get(sequence_id),
                "expected_file_id": expected_file_id,
                "actual_file_id": metadata.get("active_file_id"),
                "allowed_tables": allowed_tables,
                "query_plan": query_plan,
                "sql": sql,
                "sql_present": bool(sql),
                "file_scope_validated": metadata.get("file_scope_validated"),
                "passed": passed,
            }
            all_results.append(result)
            histories[sequence_id].append(
                {
                    "turn_index": turn_index,
                    "question": case["question"],
                    "response_type": response.response_type,
                    "execution_mode": result["execution_mode"],
                    "active_file_id": result["actual_file_id"],
                    "passed": passed,
                }
            )
            previous_active[sequence_id] = result["actual_file_id"]
            if not passed:
                inventory.append(_inventory_item(result, history_before, allowed_catalog))

    summary = {
        "total_cases": len(all_results),
        "failed": len(inventory),
        "passed": len(all_results) - len(inventory),
        "accuracy": round((len(all_results) - len(inventory)) / max(1, len(all_results)), 4),
        "by_failure_category": dict(Counter(item["failure_category"] for item in inventory)),
        "by_root_cause": dict(Counter(item["root_cause"] for item in inventory)),
        "cross_file_sql_count": sum(1 for item in inventory if item["failure_category"] == "QUERY_PLAN_FILE_SCOPE_ERROR" and item.get("sql")),
        "cross_file_provenance_count": sum(1 for item in inventory if item["failure_category"] == "RESULT_PROVENANCE_ERROR"),
    }
    (ARTIFACTS / "file_scoped_failure_inventory.json").write_text(
        json.dumps({"summary": summary, "failures": inventory}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))


def _inventory_item(result: dict[str, Any], history_before: list[dict[str, Any]], catalog: dict[str, Any]) -> dict[str, Any]:
    plan = result.get("query_plan") if isinstance(result.get("query_plan"), dict) else {}
    expected_tables = list(result.get("allowed_tables") or [])
    actual_tables = [str(item) for item in plan.get("tables", [])] if plan else []
    failure_category, root_cause = _classify(result)
    return {
        "case_id": result["id"],
        "conversation_id": result["conversation_id"],
        "turn_index": result["turn_index"],
        "active_file_id": result.get("actual_file_id") or "",
        "active_file_name": result.get("active_file_name") or "",
        "previous_active_file_id": result.get("previous_active_file_id"),
        "expected_file_id": result.get("expected_file_id") or "",
        "actual_file_id": result.get("actual_file_id") or "",
        "question": result["question"],
        "conversation_history": history_before,
        "expected_mode": result["expected_response_type"],
        "actual_mode": result.get("execution_mode") or "",
        "expected_intent": result["expected_response_type"],
        "actual_intent": result["actual_response_type"],
        "expected_tables": expected_tables,
        "actual_tables": actual_tables,
        "allowed_tables": result.get("allowed_tables") or [],
        "catalog_file_id": _catalog_file_id(catalog),
        "expected_metrics": _expected_metrics(result["question"]),
        "actual_metrics": plan.get("metrics", []) if plan else [],
        "expected_dimensions": _expected_dimensions(result["question"]),
        "actual_dimensions": plan.get("dimensions", []) if plan else [],
        "expected_filters": [],
        "actual_filters": plan.get("filters", []) if plan else [],
        "query_plan": result.get("query_plan"),
        "sql": result.get("sql"),
        "result_file_ids": [],
        "provenance_valid": bool(result.get("file_scope_validated")) and (not actual_tables or set(actual_tables).issubset(set(result.get("allowed_tables") or []))),
        "failure_category": failure_category,
        "root_cause": root_cause,
    }


def _classify(result: dict[str, Any]) -> tuple[str, str]:
    question = str(result.get("question") or "").lower()
    category = result.get("category")
    actual = result.get("actual_response_type")
    mode = result.get("execution_mode")
    if result.get("actual_file_id") != result.get("expected_file_id"):
        return "ACTIVE_FILE_NOT_RESOLVED", "Active file in response did not match benchmark-selected file."
    if result.get("file_scope_validated") is False and category == "multipart":
        return "SEMANTIC_FIELD_MAPPING_ERROR", "Loss-scoped query used downtime/machine language that router treated as another file reference."
    if category == "real_llm_candidate" and actual == "data_quality":
        return "ROUTER_MODE_ERROR", "Freeform analytical anomaly request was intercepted by metadata data-quality routing."
    if category == "real_llm_candidate" and actual == "clarification":
        return "ROUTER_MODE_ERROR", "Freeform insight request did not enter semantic analytical planning."
    if category == "safe_failure" and actual == "refusal":
        return "BENCHMARK_ORACLE_ERROR", "Unsafe SQL request is safely refused; benchmark expected response_type error."
    if category == "context_sequence" and actual == "schema":
        return "BENCHMARK_ORACLE_ERROR", "Sequence asks 'Xem schema' but benchmark expects analytical table."
    if "downtime" in question and result.get("active_file_key") == "loss":
        return "SEMANTIC_FIELD_MAPPING_ERROR", "Question uses downtime term while active file is Loss_Assignment."
    if result.get("query_plan") and not set(result.get("query_plan", {}).get("tables", [])).issubset(set(result.get("allowed_tables") or [])):
        return "QUERY_PLAN_FILE_SCOPE_ERROR", "QueryPlan selected a table outside active file allowlist."
    if mode == "CLARIFICATION":
        return "ROUTER_MODE_ERROR", "Router chose clarification for benchmark case expecting executable analysis."
    return "EXPECTED_RESULT_ERROR", "Response did not match benchmark expected type."


def _catalog_file_id(catalog: dict[str, Any]) -> str:
    for table in catalog.get("tables", []):
        profile = table.get("profile") if isinstance(table.get("profile"), dict) else {}
        value = table.get("file_id") or table.get("source_file_id") or profile.get("source_file_id")
        if value:
            return str(value)
        for col in table.get("columns", []):
            if col.get("normalized_name") == "_source_file_id":
                samples = col.get("sample_values") or []
                if samples:
                    return str(samples[0])
    return ""


def _expected_metrics(question: str) -> list[str]:
    q = question.lower()
    metrics = []
    if any(term in q for term in ["downtime", "thoi luong", "thoi gian"]):
        metrics.append("total_duration_seconds")
    if any(term in q for term in ["so lan", "dem"]):
        metrics.append("row_count")
    if "gia tri can" in q:
        metrics.append("total_gia_tri_can")
    return metrics


def _expected_dimensions(question: str) -> list[str]:
    q = question.lower()
    dims = []
    if "may" in q:
        dims.append("machine")
    if "nguyen nhan" in q:
        dims.append("loss_name")
    if "nhom" in q:
        dims.append("loss_group")
    if "cong" in q:
        dims.append("cong")
    return dims


if __name__ == "__main__":
    main()
