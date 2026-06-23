"""Benchmark REAL_LLM routing policy by intent category.

The benchmark uses the product application service with a temporary memory DB. It does
not let the model generate SQL directly; it only verifies whether semantic planning or
grounded composition actually crossed the Ollama client boundary when policy requires it.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files


ARTIFACTS = ROOT / "artifacts"


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "A01",
            "category": "exact_deterministic",
            "file": "machine",
            "message": "File có bao nhiêu bản ghi?",
            "expected_llm_call": False,
            "expected_route": "deterministic",
        },
        {
            "id": "A02",
            "category": "exact_deterministic",
            "file": "machine",
            "message": "File có những cột nào?",
            "expected_llm_call": False,
            "expected_route": "deterministic",
        },
        {
            "id": "A03",
            "category": "exact_deterministic",
            "file": "machine",
            "message": "No. 1 là bản ghi gì?",
            "expected_llm_call": False,
            "expected_route": "deterministic",
        },
        {
            "id": "A04",
            "category": "exact_deterministic",
            "file": "machine",
            "message": "Máy nào có tổng downtime cao nhất?",
            "expected_llm_call": False,
            "expected_route": "deterministic",
        },
        {
            "id": "B01",
            "category": "open_ended_analysis",
            "file": "machine",
            "message": "Dựa trên toàn bộ dữ liệu, hãy giải thích ba điểm đáng chú ý nhất, so sánh chúng và nêu giới hạn của kết luận.",
            "expected_llm_call": True,
            "expected_route": "semantic",
        },
        {
            "id": "B02",
            "category": "multipart_analytics",
            "file": "loss",
            "message": "Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét.",
            "expected_llm_call": True,
            "expected_route": "semantic",
        },
        {
            "id": "B03",
            "category": "open_ended_analysis",
            "file": "machine",
            "message": "Coi thử trong data này có điều gì bất thường hoặc đáng quan tâm, giải thích dễ hiểu giúp tôi.",
            "expected_llm_call": True,
            "expected_route": "semantic",
        },
        {
            "id": "B04",
            "category": "multipart_analytics",
            "file": "machine",
            "message": "Top 5 máy theo tổng downtime, thêm số lần dừng, thời lượng trung bình và nhận xét.",
            "expected_llm_call": True,
            "expected_route": "semantic",
        },
        {
            "id": "B05",
            "category": "topic_restore",
            "file": "machine",
            "setup": ["Cho tôi top 5 máy theo tổng downtime."],
            "message": "Quay lại kết quả lúc nãy, thêm số lần ghi nhận, tỷ trọng và giải thích sự khác biệt.",
            "expected_llm_call": True,
            "expected_route": "semantic",
        },
        {
            "id": "C01",
            "category": "pending_state_exact_slot",
            "file": "machine",
            "setup": ["Vẽ biểu đồ tổng quan"],
            "message": "Số lần dừng.",
            "expected_llm_call": False,
            "expected_route": "clarification_resolution",
        },
        {
            "id": "C02",
            "category": "pending_state_new_request",
            "file": "machine",
            "setup": ["Vẽ biểu đồ tổng quan"],
            "message": "Bỏ biểu đồ đi, phân tích ba nguyên nhân phổ biến nhất và giải thích kết quả.",
            "expected_llm_call": True,
            "expected_route": "semantic",
        },
        {
            "id": "D01",
            "category": "model_unavailable",
            "file": "machine",
            "message": "Top 5 máy theo tổng downtime, thêm nhận xét.",
            "expected_llm_call": True,
            "expected_route": "semantic_error_or_fallback",
            "force_model_down": True,
        },
    ]


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    settings = get_settings()
    files = list_uploaded_files()
    records = {
        "machine": _record(files, "Machine_Downtime"),
        "loss": _record(files, "Loss_Assignment"),
        "entry": _record(files, "EntryTransaction"),
    }
    missing = [key for key, value in records.items() if value is None and key != "entry"]
    if missing:
        raise SystemExit(f"Missing ready uploaded files for: {', '.join(missing)}")

    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="gopak-llm-invocation-", ignore_cleanup_errors=True) as tmp:
        memory_db = Path(tmp) / "memory.db"
        for case in _cases():
            case_settings = settings
            if case.get("force_model_down"):
                case_settings = replace(settings, ollama_base_url="http://127.0.0.1:9")
            memory = ConversationMemoryService(
                db_path=memory_db,
                cache_root=settings.cache_dir,
                enabled=True,
                recent_turns_limit=settings.recent_turns_limit,
            )
            app = ChatApplicationService(settings=case_settings, memory_service=memory)
            record = records[case["file"]]
            conv = app.create_conversation(case["id"], source_file_id=str(record["id"]))
            for setup_message in case.get("setup", []):
                app.process_message(conv.id, setup_message, debug=True, source_file_id=str(record["id"]))
            response = app.process_message(conv.id, case["message"], debug=True, source_file_id=str(record["id"]))
            metadata = response.metadata or {}
            actual_llm_call = bool(metadata.get("llm_called") or metadata.get("grounded_composer_called"))
            structured_output_valid = bool(metadata.get("structured_output_valid", True))
            fallback_used = bool(metadata.get("fallback_used"))
            fallback_reason = metadata.get("fallback_reason")
            final_response_valid = response.response_type not in {"error"} and bool(response.summary or response.primary_value or response.table or response.chart)
            passed = (
                actual_llm_call == bool(case["expected_llm_call"])
                and final_response_valid
                and not (fallback_used and not actual_llm_call)
            )
            if case.get("force_model_down"):
                passed = actual_llm_call and bool(fallback_reason or response.response_type in {"error", "table", "chart", "text"})
            entry = {
                "id": case["id"],
                "category": case["category"],
                "message": case["message"],
                "expected_llm_call": bool(case["expected_llm_call"]),
                "actual_llm_call": actual_llm_call,
                "expected_route": case["expected_route"],
                "actual_route": metadata.get("execution_mode") or metadata.get("mode") or response.response_type,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "structured_output_valid": structured_output_valid,
                "final_response_valid": final_response_valid,
                "response_type": response.response_type,
                "passed": passed,
            }
            results.append(entry)
            trace = {
                "request_id": response.message_id,
                "conversation_id": conv.id,
                "message_id": response.message_id,
                "matched_rule": metadata.get("routing_reason") or "",
                "deterministic_confidence": metadata.get("router_confidence"),
                "semantic_candidate": bool(case["expected_llm_call"]),
                "semantic_resolver_called": actual_llm_call and entry["actual_route"] == "REAL_LLM",
                "llm_request_started": bool(metadata.get("llm_request_started") or actual_llm_call),
                "llm_request_completed": bool(metadata.get("llm_request_completed", actual_llm_call and not fallback_used)),
                "llm_model": metadata.get("llm_model") or metadata.get("composer_model"),
                "llm_latency_ms": metadata.get("llm_latency_ms") or (metadata.get("latency_ms") or {}).get("llm"),
                "structured_output_valid": structured_output_valid,
                "schema_validation_errors": metadata.get("schema_validation_errors") or [],
                "retry_count": int(metadata.get("retry_count") or 0),
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "final_route": entry["actual_route"],
            }
            traces.append(trace)
            if fallback_used or fallback_reason:
                fallbacks.append({**entry, "trace": trace})

    summary = _summarize(results, traces, fallbacks)
    baseline = _load_baseline()
    (ARTIFACTS / "llm_invocation_baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "llm_invocation_final_results.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "llm_fallback_audit.json").write_text(json.dumps({"summary": summary, "fallbacks": fallbacks}, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "llm_call_traces.json").write_text(json.dumps({"summary": summary, "traces": traces}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["failed_cases"]:
        raise SystemExit(2)


def _record(files: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    return next((item for item in files if needle in str(item.get("filename")) and item.get("status") == "ready"), None)


def _summarize(results: list[dict[str, Any]], traces: list[dict[str, Any]], fallbacks: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_category.setdefault(item["category"], {"total": 0, "passed": 0, "llm_calls": 0})
        bucket["total"] += 1
        bucket["passed"] += int(item["passed"])
        bucket["llm_calls"] += int(item["actual_llm_call"])
    semantic = [item for item in results if item["expected_llm_call"] and item["category"] != "model_unavailable"]
    deterministic = [item for item in results if not item["expected_llm_call"]]
    latencies = [float(item["llm_latency_ms"]) for item in traces if item.get("llm_latency_ms") is not None]
    p50 = median(latencies) if latencies else 0.0
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0.0
    return {
        "total_cases": len(results),
        "passed_cases": sum(1 for item in results if item["passed"]),
        "failed_cases": [item["id"] for item in results if not item["passed"]],
        "by_category": by_category,
        "semantic_real_llm_call_rate": _ratio(sum(1 for item in semantic if item["actual_llm_call"]), len(semantic)),
        "deterministic_unnecessary_llm_calls": sum(1 for item in deterministic if item["actual_llm_call"]),
        "silent_fallback_count": sum(1 for item in fallbacks if not item["actual_llm_call"]),
        "fallback_count": len(fallbacks),
        "fallback_reason_coverage": _ratio(sum(1 for item in fallbacks if item.get("fallback_reason")), len(fallbacks)),
        "structured_output_validity": _ratio(sum(1 for item in semantic if item["structured_output_valid"]), len(semantic)),
        "llm_p50_latency_ms": round(p50, 1),
        "llm_p95_latency_ms": round(p95, 1),
    }


def _load_baseline() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:artifacts/demo_conversation_seed_results.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            payload = json.loads(result.stdout)
            return {"source": "HEAD:artifacts/demo_conversation_seed_results.json", "summary": payload.get("summary", payload)}
    except Exception:
        pass
    return {"source": "unavailable", "summary": {}}


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


if __name__ == "__main__":
    main()
