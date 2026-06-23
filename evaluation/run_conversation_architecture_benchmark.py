from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CASES_PATH = ROOT / "evaluation" / "conversation_architecture_cases.json"
ARTIFACTS = ROOT / "artifacts"

from src.application.chat_service import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def run_case(case: dict[str, Any], subset: str) -> dict[str, Any]:
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="gopak-conv-bench-", ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        memory = ConversationMemoryService(
            db_path=tmp_path / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        files = list_uploaded_files()
        file_id = resolve_file_id(files, case.get("file_key", "machine"))
        conv = app.create_conversation(case.get("id"), source_file_id=file_id) if file_id else app.create_conversation(case.get("id"))
        current_file_id = file_id

        turns = []
        latencies = []
        repeated_loop = False
        last_clarification = None
        passed = True
        failure_reasons = []
        for index, turn in enumerate(case.get("turns", [])):
            if turn.get("restart_before"):
                memory = ConversationMemoryService(
                    db_path=tmp_path / "memory.db",
                    cache_root=settings.cache_dir,
                    enabled=True,
                    recent_turns_limit=settings.recent_turns_limit,
                )
                app = ChatApplicationService(settings=settings, memory_service=memory)
            if turn.get("select_file"):
                file_id = resolve_file_id(files, turn["select_file"])
                if file_id and file_id != current_file_id:
                    conv = app.create_conversation(f"{case.get('id')}-{index}", source_file_id=file_id)
                    current_file_id = file_id
                elif file_id:
                    app.set_active_file(conv.id, file_id)
            started = perf_counter()
            response = app.process_message(conv.id, turn["message"], debug=True)
            latency = (perf_counter() - started) * 1000
            latencies.append(latency)
            metadata = response.metadata or {}
            sql = bool((metadata.get("debug") or {}).get("sql") or metadata.get("generated_sql"))
            if response.response_type == "clarification":
                text = response.summary or response.title
                if last_clarification == text:
                    repeated_loop = True
                last_clarification = text
            else:
                last_clarification = None
            checks = {
                "response_type": response.response_type,
                "execution_mode": metadata.get("execution_mode"),
                "llm_called": bool(metadata.get("llm_called")),
                "sql_executed": sql,
                "active_file_id": metadata.get("active_file_id"),
                "pending_after": bool(metadata.get("pending_clarification_after")),
            }
            expected = turn.get("expect", {})
            ok = True
            if "response_type" in expected and response.response_type != expected["response_type"]:
                ok = False
                failure_reasons.append(f"turn {index}: response_type expected {expected['response_type']} got {response.response_type}")
            if "sql_executed" in expected and sql != expected["sql_executed"]:
                ok = False
                failure_reasons.append(f"turn {index}: sql expected {expected['sql_executed']} got {sql}")
            if "pending_after" in expected and checks["pending_after"] != expected["pending_after"]:
                ok = False
                failure_reasons.append(f"turn {index}: pending expected {expected['pending_after']} got {checks['pending_after']}")
            if "llm_called" in expected and checks["llm_called"] != expected["llm_called"]:
                ok = False
                failure_reasons.append(f"turn {index}: llm expected {expected['llm_called']} got {checks['llm_called']}")
            passed = passed and ok
            turns.append({"message": turn["message"], "latency_ms": round(latency, 1), "checks": checks, "passed": ok})
        if repeated_loop:
            passed = False
            failure_reasons.append("repeated clarification loop")
        return {
            "id": case["id"],
            "set": subset,
            "category": case.get("category"),
            "passed": passed,
            "failure_reasons": failure_reasons,
            "repeated_loop": repeated_loop,
            "turns": turns,
            "latency_ms": round(sum(latencies), 1),
        }


def resolve_file_id(files: list[dict[str, Any]], key: str) -> str | None:
    terms = {
        "machine": "Machine_Downtime",
        "loss": "Loss_Assignment",
        "entry": "EntryTransaction",
    }
    needle = terms.get(key, key)
    record = next((item for item in files if needle in item.get("filename", "")), None)
    return str(record["id"]) if record else None


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    latencies = [item["latency_ms"] for item in results]
    return {
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "repeated_clarification_loops": sum(1 for item in results if item.get("repeated_loop")),
        "p50_latency_ms": round(statistics.median(latencies), 1) if latencies else 0,
        "p95_latency_ms": round(statistics.quantiles(latencies, n=20)[18], 1) if len(latencies) >= 20 else (max(latencies) if latencies else 0),
        "llm_calls": sum(1 for item in results for turn in item["turns"] if turn["checks"].get("llm_called")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["development", "holdout", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cases = [case for case in load_cases() if args.set == "all" or case.get("set") == args.set]
    if args.limit:
        cases = cases[: args.limit]
    results = [run_case(case, case.get("set", "development")) for case in cases]
    ARTIFACTS.mkdir(exist_ok=True)
    if args.set in {"development", "all"}:
        dev = [item for item in results if item["set"] == "development"]
        if dev:
            (ARTIFACTS / "conversation_benchmark_development.json").write_text(json.dumps({"summary": summarize(dev), "results": dev}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if args.set in {"holdout", "all"}:
        holdout = [item for item in results if item["set"] == "holdout"]
        if holdout:
            (ARTIFACTS / "conversation_benchmark_holdout.json").write_text(json.dumps({"summary": summarize(holdout), "results": holdout}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "conversation_architecture_candidate_results.json").write_text(json.dumps({"summary": summarize(results), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summarize(results), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
