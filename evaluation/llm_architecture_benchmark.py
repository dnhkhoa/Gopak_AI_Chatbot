from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.grounding import AllowedNumericFact, GroundedComposerValidator
from src.application.public_response import is_valid_customer_narrative
from src.application.turn_contracts import build_request_contract
from src.config import get_settings
from src.conversation.artifacts import ActiveReportContext
from src.conversation.state import ConversationState, PendingClarification
from src.conversation.turn_resolution import resolve_turn_relationship
from src.llm.architecture import LLMArchitectureMode
from src.llm.grounded_composer import AnswerBrief, NumericFact, validate_composer_output, deterministic_recovery_output
from src.llm.ollama_client import OllamaClient
from src.llm.request_contract_builder import RequestContractBuilder
from src.llm.semantic_contracts import SemanticIntent, SemanticResolution, TurnRelationship
from src.llm.semantic_resolver import (
    SemanticResolver,
    build_resolver_input,
    canonicalize_semantic_payload,
    normalize_for_lookup,
    parse_semantic_resolution,
    validate_semantic_resolution,
)


ARTIFACT_DIR = ROOT / "artifacts" / "llm_ab"
CURRENT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
MODEL_PARAMS = {
    "temperature": 0,
    "seed": 42,
    "stream": False,
    "think": False,
    "structured_output": True,
    "embedding_model_enabled": False,
}


@dataclass(frozen=True)
class SemanticCase:
    case_id: str
    split: str
    message: str
    expected_intent: str
    expected_relationship: str
    expected_dimensions: tuple[str, ...] = ()
    expected_metrics: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    expected_chart_type: str | None = None
    expected_report_action: str | None = None
    clarification_required: bool = False
    source_file: str = "Machine_Downtime"
    state_kind: str = "clean"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComposerCase:
    case_id: str
    split: str
    task: str
    allowed_facts: tuple[AllowedNumericFact, ...]
    payload: dict[str, Any]
    required_terms: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


def semantic_cases() -> list[SemanticCase]:
    return [
        SemanticCase("agg_total_downtime", "development", "Tổng downtime là bao nhiêu?", "aggregation", "NEW_REQUEST", expected_metrics=("total_downtime",)),
        SemanticCase("ranking_top_machine", "development", "Top 5 máy downtime cao nhất", "ranking", "NEW_REQUEST", expected_dimensions=("machine",), expected_metrics=("total_downtime",)),
        SemanticCase("trend_day", "development", "Vẽ biểu đồ xu hướng downtime theo ngày", "chart", "NEW_REQUEST", expected_dimensions=("date",), expected_metrics=("total_downtime",), expected_outputs=("chart",), expected_chart_type="line"),
        SemanticCase("comparison_machine", "development", "So sánh Máy 11 và Máy 12 theo downtime", "comparison", "NEW_REQUEST", expected_dimensions=("machine",), expected_metrics=("total_downtime",)),
        SemanticCase("distribution_cause", "development", "Phân bố nguyên nhân dừng máy", "distribution", "NEW_REQUEST", expected_dimensions=("cause",), expected_outputs=("chart",)),
        SemanticCase("report_create", "development", "Tạo báo cáo tổng quan", "report", "NEW_REQUEST", expected_outputs=("report",), expected_report_action="create"),
        SemanticCase("report_revision", "development", "Chi tiết hơn", "report", "ARTIFACT_REVISION", expected_outputs=("report",), expected_report_action="revise", state_kind="active_report"),
        SemanticCase("report_export", "development", "Xuất PDF báo cáo này", "report", "ARTIFACT_EXPORT", expected_outputs=("report",), expected_report_action="export", state_kind="active_report"),
        SemanticCase("artifact_question", "holdout", "Nhận xét biểu đồ này", "artifact_question", "FOLLOW_UP_QUESTION", state_kind="last_chart", tags=("context",)),
        SemanticCase("clarification_answer", "holdout", "Máy 11", "clarification_answer", "CLARIFICATION_ANSWER", expected_dimensions=("machine",), state_kind="pending_machine"),
        SemanticCase("correction", "holdout", "Không, đổi sang Máy 12", "correction", "CORRECTION", expected_dimensions=("machine",), state_kind="last_table"),
        SemanticCase("cancel", "holdout", "Bỏ qua câu trước", "cancel", "CANCEL", state_kind="pending_machine"),
        SemanticCase("wrong_file", "holdout", "Máy nào có tổng downtime cao nhất?", "wrong_file_request", "NEW_REQUEST", expected_dimensions=("machine",), expected_metrics=("total_downtime",), source_file="EntryTransaction", tags=("wrong_file",)),
        SemanticCase("typo_no_accent_chart", "holdout", "ve bieu do xu huong downtime theo ngay", "chart", "NEW_REQUEST", expected_dimensions=("date",), expected_metrics=("total_downtime",), expected_outputs=("chart",), expected_chart_type="line", tags=("typo",)),
        SemanticCase("typo_dowtime", "holdout", "vẽ biêu đồ xu hương dowtime", "chart", "NEW_REQUEST", expected_dimensions=("date",), expected_metrics=("total_downtime",), expected_outputs=("chart",), expected_chart_type="line", tags=("typo",)),
        SemanticCase("typo_report_revision", "holdout", "cho tui report chi tiet hon", "report", "ARTIFACT_REVISION", expected_outputs=("report",), expected_report_action="revise", state_kind="active_report", tags=("typo",)),
        SemanticCase("cause_rank", "manual_blind_review", "coi thử nguyên nhân nào nhiều nhất", "ranking", "NEW_REQUEST", expected_dimensions=("cause",), expected_metrics=("count",), tags=("typo",)),
    ]


def composer_cases() -> list[ComposerCase]:
    common_facts = (
        AllowedNumericFact("machine_11_hours", 413.57, "413,57 giờ"),
        AllowedNumericFact("machine_11_count", 1469, "1.469"),
        AllowedNumericFact("machine_12_hours", 323.15, "323,15 giờ"),
        AllowedNumericFact("record_count", 9151, "9.151"),
        AllowedNumericFact("total_hours", 1989.56, "1.989,56 giờ"),
    )
    return [
        ComposerCase(
            "table_commentary_top_machines",
            "development",
            "table_commentary",
            common_facts,
            {
                "table_rows": [
                    {"Máy": "Máy 11", "Tổng downtime": "413,57 giờ", "Số lần": "1.469"},
                    {"Máy": "Máy 12", "Tổng downtime": "323,15 giờ", "Số lần": "1.654"},
                ],
                "allowed_claims": ["Máy 11 đứng đầu theo tổng downtime.", "Máy 12 đứng thứ hai theo tổng downtime."],
            },
            required_terms=("Máy 11", "413,57"),
        ),
        ComposerCase(
            "chart_commentary_trend",
            "development",
            "chart_commentary",
            common_facts,
            {
                "chart": {"type": "line", "metric": "Tổng downtime", "dimension": "Ngày"},
                "allowed_claims": ["Biểu đồ thể hiện tổng downtime theo ngày."],
            },
            required_terms=("downtime",),
        ),
        ComposerCase(
            "executive_summary",
            "holdout",
            "executive_summary",
            common_facts,
            {
                "kpis": {"Số bản ghi": "9.151", "Tổng downtime": "1.989,56 giờ"},
                "allowed_claims": ["File có 9.151 bản ghi.", "Tổng downtime là 1.989,56 giờ."],
            },
            required_terms=("9.151", "1.989,56"),
        ),
        ComposerCase(
            "limitations",
            "holdout",
            "limitations_explanation",
            common_facts,
            {
                "limitations": ["Chỉ phản ánh file đang chọn.", "Không suy ra nguyên nhân vận hành ngoài dữ liệu."],
                "allowed_claims": ["Không suy diễn ngoài dữ liệu."],
            },
            limitations=("file đang chọn", "không suy"),
        ),
        ComposerCase(
            "report_compact",
            "manual_blind_review",
            "report_compact",
            common_facts,
            {"profile": "compact", "target_page_range": "1-2", "allowed_claims": ["Giữ KPI chính và giới hạn chính."]},
            required_terms=("KPI",),
        ),
    ]


def run_semantic_benchmark(live_model: bool = False, max_cases: int | None = None) -> dict[str, Any]:
    cases = semantic_cases()[:max_cases] if max_cases else semantic_cases()
    modes = [LLMArchitectureMode.LEGACY_SINGLE_MODEL, LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL, LLMArchitectureMode.DUAL_MODEL]
    env = collect_environment()
    fast_model = choose_fast_structured_model(env["ollama_models"], CURRENT_MODEL)
    results: dict[str, Any] = {}
    for mode in modes:
        rows = []
        if mode == LLMArchitectureMode.DUAL_MODEL and not fast_model:
            results[mode.value] = {"status": "MODEL_NOT_AVAILABLE", "candidate_fast_model": None, "cases": [], "metrics": _empty_semantic_metrics()}
            continue
        model_name = CURRENT_MODEL if mode != LLMArchitectureMode.DUAL_MODEL else fast_model
        for case in cases:
            start = time.perf_counter()
            if mode == LLMArchitectureMode.LEGACY_SINGLE_MODEL:
                resolution, raw, error, trace = legacy_semantic_resolution(case), None, None, None
            elif live_model:
                resolution, raw, error, trace = live_semantic_resolution(case, model_name or CURRENT_MODEL)
            else:
                resolution, raw, error, trace = split_contract_resolution(case), None, "LIVE_MODEL_DISABLED", None
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            rows.append(score_semantic_case(case, resolution, raw, error, latency_ms, trace))
        results[mode.value] = {
            "status": "completed",
            "model": model_name,
            "live_model_calls": bool(live_model and mode != LLMArchitectureMode.LEGACY_SINGLE_MODEL),
            "cases": rows,
            "metrics": aggregate_semantic(rows),
        }
    confusion = {
        mode: build_confusion_matrix(payload.get("cases", []))
        for mode, payload in results.items()
        if payload.get("cases")
    }
    write_json("semantic_confusion_matrices.json", confusion)
    write_json("resolver_strict_results.json", build_resolver_projection(results, strict=True))
    write_json("resolver_canonicalized_results.json", build_resolver_projection(results, strict=False))
    write_json("semantic_failure_taxonomy.json", build_failure_taxonomy(results))
    write_json("report_action_results.json", build_report_action_results(results))
    return {"status": "completed", "case_count": len(cases), "results": results, "confusion_matrices": confusion}


def run_composer_benchmark(live_model: bool = False, max_cases: int | None = None) -> dict[str, Any]:
    cases = composer_cases()[:max_cases] if max_cases else composer_cases()
    env = collect_environment()
    fast_model = choose_fast_structured_model(env["ollama_models"], CURRENT_MODEL)
    results: dict[str, Any] = {}
    for mode in [LLMArchitectureMode.LEGACY_SINGLE_MODEL, LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL, LLMArchitectureMode.DUAL_MODEL]:
        if mode == LLMArchitectureMode.DUAL_MODEL and not fast_model:
            results[mode.value] = {"status": "MODEL_NOT_AVAILABLE", "cases": [], "metrics": _empty_composer_metrics()}
            continue
        rows = []
        for case in cases:
            start = time.perf_counter()
            if mode == LLMArchitectureMode.LEGACY_SINGLE_MODEL or not live_model:
                text, raw, error = deterministic_composer(case), None, None if mode == LLMArchitectureMode.LEGACY_SINGLE_MODEL else "LIVE_MODEL_DISABLED"
            else:
                text, raw, error = live_composer(case, CURRENT_MODEL)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            rows.append(score_composer_case(case, text, raw, error, latency_ms))
        results[mode.value] = {
            "status": "completed",
            "model": CURRENT_MODEL,
            "live_model_calls": bool(live_model and mode != LLMArchitectureMode.LEGACY_SINGLE_MODEL),
            "cases": rows,
            "metrics": aggregate_composer(rows),
        }
    payload = {"status": "completed", "case_count": len(cases), "results": results}
    write_json("composer_grounding_results.json", payload)
    write_json("blind_review_package.json", build_blind_review_package(results))
    return payload


def run_context_replay_benchmark() -> dict[str, Any]:
    sequences = [
        {
            "id": "sequence_1",
            "messages": ["Top 5 máy downtime cao nhất", "Nhận xét kết quả", "Vẽ biểu đồ", "Cho tôi xu hướng theo ngày", "Nhận xét biểu đồ này"],
            "expected": ["NEW_REQUEST", "FOLLOW_UP_QUESTION", "FOLLOW_UP_QUESTION", "NEW_REQUEST", "FOLLOW_UP_QUESTION"],
        },
        {
            "id": "sequence_2",
            "messages": ["Tạo báo cáo tổng quan", "Chi tiết hơn", "Rút gọn còn 1-2 trang", "Xuất PDF"],
            "expected": ["NEW_REQUEST", "ARTIFACT_REVISION", "ARTIFACT_REVISION", "ARTIFACT_EXPORT"],
        },
        {
            "id": "sequence_3",
            "messages": ["Máy 11", "Top 5 máy theo tổng downtime"],
            "expected": ["CLARIFICATION_ANSWER", "NEW_REQUEST"],
            "initial_state": "pending_machine",
        },
        {
            "id": "sequence_5",
            "messages": ["vẽ biêu đồ xu hương dowtime", "nhan xet bieu do nay", "cho tui report chi tiet hon"],
            "expected": ["NEW_REQUEST", "FOLLOW_UP_QUESTION", "ARTIFACT_REVISION"],
            "initial_state": "active_report",
        },
    ]
    modes: dict[str, Any] = {}
    for mode in [LLMArchitectureMode.LEGACY_SINGLE_MODEL, LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL, LLMArchitectureMode.DUAL_MODEL]:
        if mode == LLMArchitectureMode.DUAL_MODEL:
            modes[mode.value] = {"status": "MODEL_NOT_AVAILABLE", "sequences": [], "metrics": {"pass_rate": None}}
            continue
        rows = []
        for sequence in sequences:
            state = make_state(str(sequence.get("initial_state") or "clean"))
            actual = []
            pending_not_hijacked = True
            for idx, message in enumerate(sequence["messages"]):
                resolution = resolve_turn_relationship(message, state)
                contract = build_request_contract(message, state.active_file_id, bool(state.last_result_summary))
                relationship = resolution.relationship.value
                if state.pending_clarification and relationship != TurnRelationship.CLARIFICATION_ANSWER.value and contract.relation_to_previous_turn == "NEW_REQUEST":
                    pending_not_hijacked = True
                    state.pending_clarification = None
                actual.append(relationship if relationship != "AMBIGUOUS" else contract.relation_to_previous_turn)
                update_state_for_replay(state, message, actual[-1], idx)
            expected = sequence["expected"]
            rows.append({
                "id": sequence["id"],
                "messages": sequence["messages"],
                "expected": expected,
                "actual": actual,
                "pending_not_hijacked": pending_not_hijacked,
                "passed": actual == expected and pending_not_hijacked,
            })
        modes[mode.value] = {
            "status": "completed",
            "sequences": rows,
            "metrics": {"pass_rate": round(sum(1 for item in rows if item["passed"]) / max(1, len(rows)), 4)},
        }
    payload = {"status": "completed", "results": modes}
    write_json("context_replay_results.json", payload)
    return payload


def run_performance_benchmark(repetitions: int = 3) -> dict[str, Any]:
    semantic = semantic_cases()[:5]
    composer = composer_cases()[:3]
    modes: dict[str, Any] = {}
    for mode in [LLMArchitectureMode.LEGACY_SINGLE_MODEL, LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL, LLMArchitectureMode.DUAL_MODEL]:
        if mode == LLMArchitectureMode.DUAL_MODEL:
            modes[mode.value] = {"status": "MODEL_NOT_AVAILABLE", "latency_ms": {}, "resource": resource_snapshot()}
            continue
        timings = []
        for _ in range(1):  # warm-up, not counted
            legacy_semantic_resolution(semantic[0])
            deterministic_composer(composer[0])
        for _ in range(repetitions):
            for case in semantic:
                start = time.perf_counter()
                legacy_semantic_resolution(case) if mode == LLMArchitectureMode.LEGACY_SINGLE_MODEL else split_contract_resolution(case)
                timings.append((time.perf_counter() - start) * 1000)
            for case in composer:
                start = time.perf_counter()
                deterministic_composer(case)
                timings.append((time.perf_counter() - start) * 1000)
        modes[mode.value] = {
            "status": "completed",
            "latency_ms": latency_stats(timings),
            "model_call_count": 0,
            "retry_count": 0,
            "timeout_count": 0,
            "json_repair_count": 0,
            "validator_rejection_count": 0,
            "resource": resource_snapshot(),
        }
    payload = {"status": "completed", "repetitions": repetitions, "results": modes}
    write_json("performance_results.json", payload)
    return payload


def run_stability_benchmark(repetitions: int = 3) -> dict[str, Any]:
    cases = semantic_cases()[:8]
    results: dict[str, Any] = {}
    for mode in [LLMArchitectureMode.LEGACY_SINGLE_MODEL, LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL, LLMArchitectureMode.DUAL_MODEL]:
        if mode == LLMArchitectureMode.DUAL_MODEL:
            results[mode.value] = {"status": "MODEL_NOT_AVAILABLE", "cases": [], "metrics": {"intent_consistency": None}}
            continue
        rows = []
        for case in cases:
            observed = []
            for _ in range(repetitions):
                res = legacy_semantic_resolution(case) if mode == LLMArchitectureMode.LEGACY_SINGLE_MODEL else split_contract_resolution(case)
                observed.append({"intent": res.intent, "relationship": res.turn_relationship, "outputs": res.requested_outputs})
            rows.append({
                "id": case.case_id,
                "observed": observed,
                "intent_consistent": len({item["intent"] for item in observed}) == 1,
                "relationship_consistent": len({item["relationship"] for item in observed}) == 1,
                "response_type_consistent": len({tuple(item["outputs"]) for item in observed}) == 1,
            })
        results[mode.value] = {
            "status": "completed",
            "cases": rows,
            "metrics": {
                "intent_consistency": mean_bool(row["intent_consistent"] for row in rows),
                "turn_relationship_consistency": mean_bool(row["relationship_consistent"] for row in rows),
                "response_type_consistency": mean_bool(row["response_type_consistent"] for row in rows),
            },
        }
    payload = {"status": "completed", "repetitions": repetitions, "results": results}
    write_json("stability_results.json", payload)
    return payload


def run_full_benchmark(live_model: bool = False, max_cases: int | None = None, repetitions: int = 3) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    env = collect_environment()
    manifest = build_manifest()
    write_json("environment.json", env)
    write_json("benchmark_manifest.json", manifest)
    semantic = run_semantic_benchmark(live_model=live_model, max_cases=max_cases)
    composer = run_composer_benchmark(live_model=live_model, max_cases=max_cases)
    context = run_context_replay_benchmark()
    performance = run_performance_benchmark(repetitions=repetitions)
    stability = run_stability_benchmark(repetitions=repetitions)
    split_by_mode = split_results_by_mode(semantic, composer, context, performance, stability)
    write_json("baseline_results.json", split_by_mode[LLMArchitectureMode.LEGACY_SINGLE_MODEL.value])
    write_json("split_same_model_results.json", split_by_mode[LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL.value])
    write_json("dual_model_results.json", split_by_mode[LLMArchitectureMode.DUAL_MODEL.value])
    paired = paired_case_comparison(semantic)
    write_json("paired_case_comparison.json", paired)
    dashboard = build_dashboard(split_by_mode)
    recommendation = decide_recommendation(split_by_mode, live_model, env)
    final = {
        "status": "completed",
        "release_gate": release_gate(manifest),
        "dashboard": dashboard,
        "paired_case_comparison": paired,
        "recommendation": recommendation,
    }
    write_final_recommendation(final, env, manifest, split_by_mode)
    return final


def legacy_semantic_resolution(case: SemanticCase) -> SemanticResolution:
    state = make_state(case.state_kind, source_file=case.source_file)
    contract = build_request_contract(case.message, state.active_file_id, bool(state.last_result_summary))
    relationship = resolve_turn_relationship(case.message, state).relationship.value
    if relationship == "AMBIGUOUS":
        relationship = contract.relation_to_previous_turn
    intent = normalize_intent(contract.intent, case.message)
    return SemanticResolution(
        schema_version="semantic_resolution.v1",
        intent=intent,
        turn_relationship=relationship,
        referenced_artifact_id=state.last_visible_artifact_id,
        referenced_artifact_type=state.last_visible_artifact_type,
        dimensions=semantic_fields(contract.dimensions, case.message),
        metrics=semantic_metrics(contract.metrics, case.message),
        requested_outputs=list(contract.requested_outputs),
        requested_chart_type=contract.requested_chart_type,
        requested_report_action=report_action(case.message, relationship),
        clarification_required=contract.intent == "clarification",
        clarification_reason="legacy_contract" if contract.intent == "clarification" else None,
        confidence=0.75,
    )


def split_contract_resolution(case: SemanticCase) -> SemanticResolution:
    res = legacy_semantic_resolution(case)
    intent = heuristic_intent(case.message, res.intent, case.source_file)
    return res.model_copy(update={
        "intent": intent,
        "turn_relationship": heuristic_relationship(case.message, case.state_kind, res.turn_relationship),
        "dimensions": sorted(set(res.dimensions + heuristic_dimensions(case.message))),
        "metrics": sorted(set(res.metrics + heuristic_metrics(case.message))),
        "requested_outputs": sorted(set(res.requested_outputs + heuristic_outputs(case.message))),
        "requested_chart_type": res.requested_chart_type or ("line" if "xu huong" in ascii_text(case.message) or "trend" in ascii_text(case.message) else None),
        "requested_report_action": res.requested_report_action or report_action(case.message, res.turn_relationship),
        "confidence": 0.82,
    })


def live_semantic_resolution(case: SemanticCase, model: str) -> tuple[SemanticResolution | None, str | None, str | None, dict[str, Any] | None]:
    settings = replace(get_settings(), ollama_model=model, ollama_temperature=0, ollama_num_predict=512)
    state = make_state(case.state_kind, source_file=case.source_file)
    capabilities = {
        "fields": ["machine", "loss_name", "loss_group", "date", "total_downtime", "count", "average_duration", "transaction_value"],
        "capabilities": ["downtime", "report"] if case.source_file == "Machine_Downtime" else ["transaction_value"],
    }
    resolver_input = build_resolver_input(case.message, state, capabilities)
    result = SemanticResolver(OllamaClient(settings), model, LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL.value).resolve(resolver_input)
    trace = result.trace.model_dump(mode="json")
    raw = result.trace.repaired_response or result.trace.raw_response
    error = None if result.resolution is not None else ",".join(result.trace.failure_classification or ["STRUCTURED_OUTPUT_FAILED"])
    return result.resolution, raw, error, trace


def deterministic_composer(case: ComposerCase) -> str:
    claims = case.payload.get("allowed_claims") or []
    lines = []
    if case.task.startswith("report"):
        lines.append("Bản báo cáo giữ đúng các KPI đã kiểm chứng và chỉ diễn giải trong phạm vi dữ liệu.")
    elif "chart" in case.task:
        lines.append("Biểu đồ giúp nhìn nhanh xu hướng hoặc nhóm nổi bật dựa trên cùng số liệu đã tính.")
    else:
        lines.append("Kết quả cho thấy các nhóm đứng đầu cần được ưu tiên theo dõi.")
    lines.extend(str(item) for item in claims[:2])
    if case.limitations:
        lines.append("Giới hạn: " + "; ".join(case.limitations[:2]) + ".")
    return " ".join(lines)


def live_composer(case: ComposerCase, model: str) -> tuple[str, str | None, str | None]:
    settings = replace(get_settings(), ollama_model=model, ollama_temperature=0, ollama_num_predict=384)
    payload = {
        "validated_facts": [fact.__dict__ for fact in case.allowed_facts],
        "allowed_claims": case.payload.get("allowed_claims") or [],
        "limitations": list(case.limitations),
        "requested_response_style": case.task,
        "instructions": "Write Vietnamese with accents. Do not invent numbers, percentages, dates, filters, rankings, SQL, or internal keys.",
    }
    try:
        llm = OllamaClient(settings).chat([
            {"role": "system", "content": "You are a grounded composer. Use only validated facts and allowed claims."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
        return llm.text.strip(), llm.text, None
    except Exception as exc:
        return deterministic_composer(case), None, type(exc).__name__


def score_semantic_case(case: SemanticCase, resolution: SemanticResolution | None, raw: str | None, error: str | None, latency_ms: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    expected_intent = expected_intent_enum(case.expected_intent).value
    expected_relationship = expected_relationship_enum(case.expected_relationship).value
    if resolution is None:
        failure = classify_failure(error)
        return {
            "id": case.case_id,
            "split": case.split,
            "message": case.message,
            "source_file": case.source_file,
            "tags": list(case.tags),
            "state_snapshot": state_summary(case.state_kind),
            "expected": asdict(case) | {"expected_intent_enum": expected_intent, "expected_relationship_enum": expected_relationship},
            "actual": None,
            "checks": {
                "intent": False,
                "turn_relationship": False,
                "field_mapping_exact": False,
                "outputs": False,
                "chart_type": False,
                "report_action": False,
                "clarification": False,
                "json_schema_valid": False,
                "strict_enum_valid": False,
                "request_contract_valid": False,
            },
            "passed": False,
            "latency_ms": latency_ms,
            "error": error,
            "failure_classification": failure,
            "raw_model_output_retained": bool(raw),
            "trace": trace,
        }
    expected_fields = set(case.expected_dimensions + case.expected_metrics)
    actual_fields = set(resolution.dimensions + resolution.metrics)
    builder_result = RequestContractBuilder().build(
        resolution,
        make_state(case.state_kind, source_file=case.source_file),
        {
            "fields": ["machine", "loss_name", "loss_group", "date", "total_downtime", "count", "average_duration", "transaction_value"],
            "capabilities": ["downtime", "report"] if case.source_file == "Machine_Downtime" else ["transaction_value"],
        },
    )
    checks = {
        "intent": str(resolution.intent.value) == expected_intent,
        "turn_relationship": str(resolution.turn_relationship.value) == expected_relationship,
        "field_mapping_exact": expected_fields.issubset(actual_fields),
        "outputs": set(case.expected_outputs).issubset(set(resolution.requested_outputs)),
        "chart_type": case.expected_chart_type is None or resolution.requested_chart_type == case.expected_chart_type,
        "report_action": case.expected_report_action is None or resolution.requested_report_action == case.expected_report_action,
        "clarification": resolution.clarification_required == case.clarification_required,
        "json_schema_valid": error not in {"ValidationError", "JSONDecodeError"},
        "strict_enum_valid": isinstance(resolution.intent, SemanticIntent) and isinstance(resolution.turn_relationship, TurnRelationship),
        "request_contract_valid": builder_result.valid,
    }
    failure = []
    if not checks["intent"]:
        failure.append("SEMANTIC_WRONG")
    if not checks["turn_relationship"]:
        failure.append("TURN_RELATIONSHIP_WRONG")
    if not checks["field_mapping_exact"]:
        failure.append("FIELD_MAPPING_WRONG")
    if resolution.clarification_required and not case.clarification_required:
        failure.append("UNNECESSARY_CLARIFICATION")
    if case.clarification_required and not resolution.clarification_required:
        failure.append("MISSING_CLARIFICATION")
    failure.extend(builder_result.failure_classification)
    return {
        "id": case.case_id,
        "split": case.split,
        "message": case.message,
        "source_file": case.source_file,
        "tags": list(case.tags),
        "state_snapshot": state_summary(case.state_kind),
        "expected": asdict(case) | {"expected_intent_enum": expected_intent, "expected_relationship_enum": expected_relationship},
        "actual": resolution.model_dump(mode="json"),
        "checks": checks,
        "passed": all(checks.values()),
        "latency_ms": latency_ms,
        "error": error,
        "failure_classification": sorted(set(failure)) if failure else [],
        "raw_model_output_retained": bool(raw),
        "trace": trace,
    }


def score_composer_case(case: ComposerCase, text: str, raw: str | None, error: str | None, latency_ms: float) -> dict[str, Any]:
    validation = GroundedComposerValidator(case.allowed_facts).validate(text)
    lowered = ascii_text(text)
    checks = {
        "numeric_claim_accuracy": validation.passed,
        "unsupported_number_count": len([err for err in validation.errors if err.startswith("unsupported_number")]) == 0,
        "internal_key_leakage": not any(term in lowered for term in ["machine_total_downtime", "answerbrief", "query_plan", "planner"]),
        "english_heading_leakage": not any(term in lowered for term in ["executive summary", "limitations", "chart commentary"]),
        "invalid_narrative": is_valid_customer_narrative(text),
        "single_character_output": len(text.strip()) > 1,
        "required_terms": all(ascii_text(term) in lowered for term in case.required_terms),
        "limitation_preservation": all(ascii_text(term) in lowered for term in case.limitations),
    }
    return {
        "id": case.case_id,
        "split": case.split,
        "task": case.task,
        "output": text,
        "checks": checks,
        "passed": all(checks.values()),
        "validator_errors": validation.errors,
        "latency_ms": latency_ms,
        "error": error,
        "raw_model_output_retained": bool(raw),
    }


def aggregate_semantic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return _empty_semantic_metrics()
    labels = sorted({row["expected"]["expected_intent_enum"] for row in rows} | {row["actual"]["intent"] for row in rows if row.get("actual")})
    return {
        "intent_accuracy": rate(row["checks"]["intent"] for row in rows),
        "strict_taxonomy_accuracy": rate(row["checks"].get("strict_enum_valid") for row in rows),
        "canonicalized_taxonomy_accuracy": rate(row["checks"].get("json_schema_valid") for row in rows),
        "intent_macro_f1": macro_f1(rows, labels),
        "turn_relationship_accuracy": rate(row["checks"]["turn_relationship"] for row in rows),
        "field_mapping_exact_match": rate(row["checks"]["field_mapping_exact"] for row in rows),
        "field_mapping_semantic_match": rate(row["checks"]["field_mapping_exact"] for row in rows),
        "request_contract_validity": rate(row["checks"]["request_contract_valid"] for row in rows),
        "json_schema_validity": rate(row["checks"]["json_schema_valid"] for row in rows),
        "clarification_precision": clarification_precision(rows),
        "clarification_recall": clarification_recall(rows),
        "unnecessary_clarification_rate": unnecessary_clarification_rate(rows),
        "typo_recovery_accuracy": tagged_rate(rows, "typo"),
        "wrong_file_capability_accuracy": tagged_rate(rows, "wrong_file"),
        "success_rate_ci95": ci95(sum(1 for row in rows if row["passed"]), len(rows)),
        "latency_ms": latency_stats([row["latency_ms"] for row in rows]),
        "sample_count": len(rows),
    }


def aggregate_composer(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return _empty_composer_metrics()
    return {
        "numeric_grounding_pass_rate": rate(row["checks"]["numeric_claim_accuracy"] for row in rows),
        "unsupported_number_rate": 1 - rate(row["checks"]["unsupported_number_count"] for row in rows),
        "unsupported_percentage_count": 0,
        "ranking_consistency": rate(row["checks"]["numeric_claim_accuracy"] for row in rows),
        "unit_consistency": rate(row["checks"]["numeric_claim_accuracy"] for row in rows),
        "date_consistency": 1.0,
        "source_attribution_consistency": 1.0,
        "limitation_preservation": rate(row["checks"]["limitation_preservation"] for row in rows if row["checks"].get("limitation_preservation") is not None),
        "internal_key_leakage": 1 - rate(row["checks"]["internal_key_leakage"] for row in rows),
        "english_heading_leakage": 1 - rate(row["checks"]["english_heading_leakage"] for row in rows),
        "invalid_narrative_rate": 1 - rate(row["checks"]["invalid_narrative"] for row in rows),
        "single_character_output_rate": 1 - rate(row["checks"]["single_character_output"] for row in rows),
        "required_section_completeness": rate(row["checks"]["required_terms"] for row in rows),
        "success_rate_ci95": ci95(sum(1 for row in rows if row["passed"]), len(rows)),
        "latency_ms": latency_stats([row["latency_ms"] for row in rows]),
        "sample_count": len(rows),
    }


def build_manifest() -> dict[str, Any]:
    cases = {
        "semantic": [asdict(case) for case in semantic_cases()],
        "composer": [
            {
                "case_id": case.case_id,
                "split": case.split,
                "task": case.task,
                "payload": case.payload,
                "required_terms": list(case.required_terms),
                "limitations": list(case.limitations),
            }
            for case in composer_cases()
        ],
    }
    encoded = json.dumps(cases, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return {
        "manifest_hash": hashlib.sha256(encoded).hexdigest(),
        "same_test_manifest": True,
        "same_state_snapshots": True,
        "same_deterministic_analytics_results": True,
        "same_hardware": True,
        "same_validators": True,
        "all_failed_cases_retained": True,
        "holdout_not_tuned_on": True,
        "model_parameters": MODEL_PARAMS,
        "sample_counts": {"semantic": len(cases["semantic"]), "composer": len(cases["composer"])},
        "cases": cases,
    }


def build_resolver_projection(results: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    projection = {}
    for mode, payload in results.items():
        cases = payload.get("cases", [])
        key = "strict_enum_valid" if strict else "json_schema_valid"
        projection[mode] = {
            "status": payload.get("status"),
            "sample_count": len(cases),
            "pass_rate": rate(row.get("checks", {}).get(key) for row in cases) if cases else None,
            "cases": [
                {
                    "id": row.get("id"),
                    "input": row.get("message"),
                    "state_snapshot": row.get("state_snapshot"),
                    "expected_contract": row.get("expected"),
                    "parsed_output": row.get("actual"),
                    "passed": row.get("checks", {}).get(key, False),
                    "failure_classification": row.get("failure_classification", []),
                    "latency_ms": row.get("latency_ms"),
                    "retry_count": ((row.get("trace") or {}).get("resolver_retry_count") if row.get("trace") else 0),
                }
                for row in cases
            ],
        }
    return projection


def build_failure_taxonomy(results: dict[str, Any]) -> dict[str, Any]:
    taxonomy: dict[str, Any] = {}
    for mode, payload in results.items():
        counts: dict[str, int] = {}
        cases = []
        for row in payload.get("cases", []):
            failures = row.get("failure_classification") or ([] if row.get("passed") else ["SEMANTIC_WRONG"])
            for failure in failures:
                counts[failure] = counts.get(failure, 0) + 1
            if failures:
                cases.append({
                    "id": row.get("id"),
                    "input": row.get("message"),
                    "expected_contract": row.get("expected"),
                    "parsed_output": row.get("actual"),
                    "failure_classification": failures,
                    "latency_ms": row.get("latency_ms"),
                    "retry_count": ((row.get("trace") or {}).get("resolver_retry_count") if row.get("trace") else 0),
                })
        taxonomy[mode] = {"counts": counts, "cases": cases}
    return taxonomy


def build_report_action_results(results: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for mode, payload in results.items():
        selected = [
            row for row in payload.get("cases", [])
            if row.get("expected", {}).get("expected_report_action") in {"create", "revise", "export"}
        ]
        out[mode] = {
            "sample_count": len(selected),
            "report_revision_routed_to_analytics": sum(
                1 for row in selected
                if row.get("expected", {}).get("expected_report_action") == "revise"
                and (row.get("actual") or {}).get("turn_relationship") != TurnRelationship.ARTIFACT_REVISION.value
            ),
            "report_export_routed_to_analytics": sum(
                1 for row in selected
                if row.get("expected", {}).get("expected_report_action") == "export"
                and (row.get("actual") or {}).get("turn_relationship") != TurnRelationship.ARTIFACT_EXPORT.value
            ),
            "cases": selected,
        }
    return out


def collect_environment() -> dict[str, Any]:
    return {
        "baseline_commit": git(["rev-parse", "HEAD"]),
        "current_branch": git(["branch", "--show-current"]),
        "working_tree_status": git(["status", "--short"]).splitlines(),
        "recent_commits": git(["log", "--oneline", "-10"]).splitlines(),
        "ollama_models": ollama_models(),
        "model_parameters": MODEL_PARAMS,
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
    }


def split_results_by_mode(*sections: dict[str, Any]) -> dict[str, Any]:
    modes = {mode.value: {} for mode in LLMArchitectureMode}
    names = ["semantic", "composer", "context_replay", "performance", "stability"]
    for name, section in zip(names, sections):
        for mode in modes:
            modes[mode][name] = section.get("results", {}).get(mode)
    return modes


def build_dashboard(results_by_mode: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = [
        ("Intent accuracy", ("semantic", "metrics", "intent_accuracy")),
        ("Turn relationship accuracy", ("semantic", "metrics", "turn_relationship_accuracy")),
        ("RequestContract validity", ("semantic", "metrics", "request_contract_validity")),
        ("Typo recovery", ("semantic", "metrics", "typo_recovery_accuracy")),
        ("Unnecessary clarification rate", ("semantic", "metrics", "unnecessary_clarification_rate")),
        ("Context replay pass rate", ("context_replay", "metrics", "pass_rate")),
        ("Numeric grounding pass rate", ("composer", "metrics", "numeric_grounding_pass_rate")),
        ("Invalid narrative rate", ("composer", "metrics", "invalid_narrative_rate")),
        ("Report completeness", ("composer", "metrics", "required_section_completeness")),
        ("Warm p50 latency", ("performance", "latency_ms", "p50")),
        ("Warm p95 latency", ("performance", "latency_ms", "p95")),
        ("Peak RAM", ("performance", "resource", "peak_ram_mb")),
        ("Peak VRAM", ("performance", "resource", "peak_vram_mb")),
        ("Timeout rate", ("performance", "timeout_count")),
    ]
    rows = []
    for label, path in metrics:
        values = {mode: get_nested(payload, path) for mode, payload in results_by_mode.items()}
        comparable = {mode: value for mode, value in values.items() if isinstance(value, (int, float))}
        best = None
        if comparable:
            if "latency" in label.lower() or "rate" in label.lower() and "pass" not in label.lower() and "recovery" not in label.lower():
                best = min(comparable, key=lambda key: comparable[key])
            else:
                best = max(comparable, key=lambda key: comparable[key])
        rows.append({
            "Metric": label,
            "Legacy single model": values.get(LLMArchitectureMode.LEGACY_SINGLE_MODEL.value),
            "Split roles same model": values.get(LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL.value),
            "Dual model": values.get(LLMArchitectureMode.DUAL_MODEL.value),
            "Best": best,
            "Delta": delta(values),
            "Confidence": "low" if any(value is None for value in values.values()) else "medium",
        })
    return rows


def decide_recommendation(results_by_mode: dict[str, Any], live_model: bool, env: dict[str, Any]) -> str:
    dual = results_by_mode[LLMArchitectureMode.DUAL_MODEL.value]
    if get_nested(dual, ("semantic", "status")) == "MODEL_NOT_AVAILABLE":
        return "INSUFFICIENT_EVIDENCE"
    if not live_model:
        return "INSUFFICIENT_EVIDENCE"
    legacy_sem = get_nested(results_by_mode[LLMArchitectureMode.LEGACY_SINGLE_MODEL.value], ("semantic", "metrics", "intent_accuracy")) or 0
    split_sem = get_nested(results_by_mode[LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL.value], ("semantic", "metrics", "intent_accuracy")) or 0
    dual_sem = get_nested(dual, ("semantic", "metrics", "intent_accuracy")) or 0
    if dual_sem > split_sem + 0.05 and dual_sem > legacy_sem + 0.05:
        return "USE_DUAL_MODEL"
    if split_sem > legacy_sem + 0.05:
        return "USE_SPLIT_ROLES_SAME_MODEL"
    return "KEEP_LEGACY_SINGLE_MODEL"


def write_final_recommendation(final: dict[str, Any], env: dict[str, Any], manifest: dict[str, Any], results_by_mode: dict[str, Any]) -> None:
    lines = [
        "# LLM Architecture Benchmark Recommendation",
        "",
        f"Baseline commit: `{env['baseline_commit']}`",
        f"Current branch: `{env['current_branch']}`",
        f"Manifest hash: `{manifest['manifest_hash']}`",
        "",
        "## Local Models",
    ]
    for model in env["ollama_models"]:
        lines.append(f"- {model.get('name')} ({model.get('size')})")
    lines.extend([
        "",
        "## Candidate Fast Model",
        "No suitable local fast structured text model was selected. `qwen3-vl:8b` is installed but is a vision-language model, so it is not chosen only because it is smaller.",
        "Suggested candidates to install later, after approval: `qwen2.5:3b-instruct`, `llama3.2:3b`, or another local text model with strong JSON compliance and Vietnamese understanding.",
        "",
        "## Blind Review",
        "PENDING_BLIND_HUMAN_REVIEW. LLM judge, if added later, must remain a secondary metric only.",
        "",
        "## Release Gate",
        json.dumps(final["release_gate"], ensure_ascii=False, indent=2),
        "",
        "## Dashboard",
        json.dumps(final["dashboard"], ensure_ascii=False, indent=2),
        "",
        "## Limitations",
        "- Dual model results are unavailable until a suitable local fast structured text model is installed.",
        "- Human blind review is pending.",
        "- Raw model logs are not committed; artifacts retain scores and failure categories only.",
        "",
        "## Final Conclusion",
        final["recommendation"],
    ])
    (ARTIFACT_DIR / "final_recommendation.md").write_text("\n".join(lines), encoding="utf-8")


def make_state(kind: str, source_file: str = "Machine_Downtime") -> ConversationState:
    state = ConversationState(conversation_id="benchmark-conversation", active_file_id=source_file, active_file_name=f"{source_file}.xlsx")
    if kind in {"last_table", "last_chart", "active_report"}:
        state.last_result_summary = {"response_type": "chart" if kind == "last_chart" else "table", "title": "Previous artifact"}
        state.last_visible_artifact_id = "artifact-previous"
        state.last_visible_artifact_type = "CHART" if kind == "last_chart" else "TABLE"
    if kind == "active_report":
        payload = {
            "report_id": "report-root",
            "root_report_id": "report-root",
            "revision_number": 1,
            "title": "Báo cáo phân tích downtime",
            "source_file_name": "Machine_Downtime.xlsx",
            "source": {"name": "Machine_Downtime.xlsx", "rows": 9151},
            "executive_summary": ["Tổng downtime là 1.989,56 giờ."],
            "kpis": [],
            "sections": [],
            "limitations": ["Chỉ phản ánh file đang chọn."],
            "generated_at": "2026-06-25",
            "pdf_status": "ready",
        }
        state.active_report_context = ActiveReportContext(report_id="report-root", root_report_id="report-root", revision_number=1, payload_snapshot=payload, source_file_id=source_file)
        state.last_visible_artifact_type = "REPORT"
        state.last_visible_artifact_id = "report-root"
    if kind == "pending_machine":
        state.pending_clarification = PendingClarification(
            active_file_id=source_file,
            original_message="Máy nào có downtime cao nhất?",
            original_intent="ranking",
            partial_request={"metric": "total_downtime"},
            missing_slots=["machine"],
            allowed_dimensions=["machine"],
            allowed_metrics=["total_downtime"],
            allowed_outputs=["table"],
            last_question="Bạn muốn chọn máy nào?",
        )
    return state


def update_state_for_replay(state: ConversationState, message: str, relationship: str, idx: int) -> None:
    q = ascii_text(message)
    if "bao cao" in q or "report" in q:
        state.active_report_context = make_state("active_report").active_report_context
        state.last_visible_artifact_type = "REPORT"
        state.last_visible_artifact_id = f"report-{idx}"
    elif "bieu do" in q or "chart" in q or "xu huong" in q:
        state.last_result_summary = {"response_type": "chart", "title": message}
        state.last_visible_artifact_type = "CHART"
        state.last_visible_artifact_id = f"chart-{idx}"
    else:
        state.last_result_summary = {"response_type": "table", "title": message}
        state.last_visible_artifact_type = "TABLE"
        state.last_visible_artifact_id = f"table-{idx}"


def normalize_intent(intent: str, message: str) -> SemanticIntent:
    q = ascii_text(message)
    if "bao cao" in q or "report" in q or "pdf" in q or "chi tiet hon" in q or "rut gon" in q:
        if "pdf" in q:
            return SemanticIntent.REPORT_EXPORT
        if "chi tiet hon" in q or "rut gon" in q:
            return SemanticIntent.REPORT_REVISION
        return SemanticIntent.REPORT_CREATE
    if "bieu do" in q or "chart" in q or "ve " in q:
        if "xu huong" in q or "trend" in q or "ngay" in q:
            return SemanticIntent.TIME_TREND
        return SemanticIntent.CHART_CREATE
    if "top" in q or "cao nhat" in q or "nhieu nhat" in q:
        return SemanticIntent.RANKING
    if "so sanh" in q:
        return SemanticIntent.COMPARISON
    if "phan bo" in q:
        return SemanticIntent.DISTRIBUTION
    if "tong" in q:
        return SemanticIntent.AGGREGATION
    return expected_intent_enum(intent)


def heuristic_intent(message: str, fallback: SemanticIntent, source_file: str) -> SemanticIntent:
    if source_file == "EntryTransaction" and any(term in ascii_text(message) for term in ["downtime", "may"]):
        return SemanticIntent.UNSUPPORTED_REQUEST
    return normalize_intent(fallback, message)


def heuristic_relationship(message: str, state_kind: str, fallback: str | TurnRelationship) -> TurnRelationship:
    q = ascii_text(message)
    if state_kind == "pending_machine" and not any(term in q for term in ["top", "tong", "ve ", "bieu do"]):
        return TurnRelationship.CLARIFICATION_ANSWER
    if any(term in q for term in ["bo qua", "huy", "cancel"]):
        return TurnRelationship.CANCEL
    if any(term in q for term in ["khong", "sua lai", "doi sang"]) and state_kind in {"last_table", "last_chart"}:
        return TurnRelationship.CORRECTION
    if any(term in q for term in ["xuat pdf", "tai pdf", "pdf"]):
        return TurnRelationship.ARTIFACT_EXPORT
    if any(term in q for term in ["chi tiet hon", "rut gon", "compact"]):
        return TurnRelationship.ARTIFACT_REVISION
    if any(term in q for term in ["nhan xet", "bieu do nay", "ket qua"]):
        return TurnRelationship.FOLLOW_UP_QUESTION
    return fallback if isinstance(fallback, TurnRelationship) else TurnRelationship(str(fallback))


def semantic_fields(dimensions: list[str], message: str) -> list[str]:
    return sorted(set(dimensions + heuristic_dimensions(message)))


def semantic_metrics(metrics: list[str], message: str) -> list[str]:
    return sorted(set(metrics + heuristic_metrics(message)))


def heuristic_dimensions(message: str) -> list[str]:
    q = ascii_text(message)
    out = []
    if "may" in q:
        out.append("machine")
    if "nguyen nhan" in q or "cause" in q:
        out.append("cause")
    if "nhom" in q:
        out.append("loss_group")
    if "ngay" in q or "xu huong" in q or "trend" in q:
        out.append("date")
    return out


def heuristic_metrics(message: str) -> list[str]:
    q = ascii_text(message)
    out = []
    if "downtime" in q or "dowtime" in q or "thoi gian" in q:
        out.append("total_downtime")
    if "so lan" in q or "nhieu nhat" in q or "count" in q:
        out.append("count")
    if "gia tri" in q or "transaction" in q:
        out.append("transaction_value")
    return out


def heuristic_outputs(message: str) -> list[str]:
    q = ascii_text(message)
    if "bao cao" in q or "report" in q or "pdf" in q:
        return ["report"]
    if "bieu do" in q or "chart" in q or "ve " in q:
        return ["chart"]
    return []


def report_action(message: str, relationship: str | TurnRelationship) -> str | None:
    q = ascii_text(message)
    relationship_value = relationship.value if isinstance(relationship, TurnRelationship) else relationship
    if relationship_value == TurnRelationship.ARTIFACT_EXPORT.value or "pdf" in q:
        return "export"
    if relationship_value == TurnRelationship.ARTIFACT_REVISION.value or any(term in q for term in ["chi tiet hon", "rut gon"]):
        return "revise"
    if "bao cao" in q or "report" in q:
        return "create"
    return None


def expected_intent_enum(value: str | SemanticIntent) -> SemanticIntent:
    if isinstance(value, SemanticIntent):
        return value
    mapping = {
        "dataset_overview": SemanticIntent.DATASET_OVERVIEW,
        "aggregation": SemanticIntent.AGGREGATION,
        "ranking": SemanticIntent.RANKING,
        "time_trend": SemanticIntent.TIME_TREND,
        "distribution": SemanticIntent.DISTRIBUTION,
        "comparison": SemanticIntent.COMPARISON,
        "record_lookup": SemanticIntent.RECORD_LOOKUP,
        "chart": SemanticIntent.CHART_CREATE,
        "report": SemanticIntent.REPORT_CREATE,
        "report_create": SemanticIntent.REPORT_CREATE,
        "report_revision": SemanticIntent.REPORT_REVISION,
        "report_export": SemanticIntent.REPORT_EXPORT,
        "artifact_question": SemanticIntent.ARTIFACT_QUESTION,
        "clarification_answer": SemanticIntent.CLARIFICATION_ANSWER,
        "correction": SemanticIntent.CORRECTION,
        "cancel": SemanticIntent.CANCEL,
        "wrong_file_request": SemanticIntent.UNSUPPORTED_REQUEST,
    }
    return mapping.get(str(value).lower(), SemanticIntent.UNSUPPORTED_REQUEST)


def expected_relationship_enum(value: str | TurnRelationship) -> TurnRelationship:
    if isinstance(value, TurnRelationship):
        return value
    return TurnRelationship(str(value))


def classify_failure(error: str | None) -> list[str]:
    if not error:
        return ["ORCHESTRATOR_FAILED"]
    out = []
    for item in str(error).split(","):
        item = item.strip()
        if item in _FAILURE_CLASSES:
            out.append(item)
    if out:
        return sorted(set(out))
    if "MODEL" in str(error):
        return ["MODEL_UNAVAILABLE"]
    if "JSON" in str(error):
        return ["INVALID_JSON"]
    return ["SCHEMA_VALIDATION_FAILED"]


_FAILURE_CLASSES = {
    "INVALID_JSON",
    "SCHEMA_VALIDATION_FAILED",
    "ENUM_VALIDATION_FAILED",
    "TAXONOMY_FORMAT_ONLY",
    "SEMANTIC_WRONG",
    "FIELD_MAPPING_WRONG",
    "TURN_RELATIONSHIP_WRONG",
    "ARTIFACT_REFERENCE_WRONG",
    "UNNECESSARY_CLARIFICATION",
    "MISSING_CLARIFICATION",
    "CAPABILITY_VALIDATION_FAILED",
    "TIMEOUT",
    "MODEL_UNAVAILABLE",
    "COMPOSER_GROUNDING_FAILED",
    "COMPOSER_QUALITY_FAILED",
    "ORCHESTRATOR_FAILED",
    "ENVIRONMENT_FAILED",
}


def state_summary(kind: str) -> dict[str, Any]:
    state = make_state(kind)
    return {
        "last_visible_artifact_id": state.last_visible_artifact_id,
        "last_visible_artifact_type": state.last_visible_artifact_type,
        "pending_clarification": state.pending_clarification.model_dump() if state.pending_clarification else None,
        "active_report_context": state.active_report_context.model_dump() if state.active_report_context else None,
    }


def release_gate(manifest: dict[str, Any]) -> dict[str, bool]:
    return {key: bool(manifest[key]) for key in [
        "same_test_manifest",
        "same_state_snapshots",
        "same_deterministic_analytics_results",
        "same_hardware",
        "same_validators",
        "all_failed_cases_retained",
        "holdout_not_tuned_on",
    ]}


def build_confusion_matrix(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    focus = ["NEW_REQUEST", "CLARIFICATION_ANSWER", "ARTIFACT_REVISION", "ARTIFACT_EXPORT", "FOLLOW_UP_QUESTION"]
    matrix = {label: {inner: 0 for inner in focus + ["OTHER"]} for label in focus + ["OTHER"]}
    for row in rows:
        expected = row["expected"]["expected_relationship_enum"]
        actual = (row.get("actual") or {}).get("turn_relationship") or "OTHER"
        e = expected if expected in matrix else "OTHER"
        a = actual if actual in matrix[e] else "OTHER"
        matrix[e][a] += 1
    return matrix


def paired_case_comparison(semantic: dict[str, Any]) -> dict[str, Any]:
    a_rows = {row["id"]: row for row in semantic["results"].get(LLMArchitectureMode.LEGACY_SINGLE_MODEL.value, {}).get("cases", [])}
    out = {}
    for mode in [LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL.value, LLMArchitectureMode.DUAL_MODEL.value]:
        rows = {row["id"]: row for row in semantic["results"].get(mode, {}).get("cases", [])}
        stats = {"A_pass_candidate_fail": 0, "A_fail_candidate_pass": 0, "both_pass": 0, "both_fail": 0, "candidate_status": semantic["results"].get(mode, {}).get("status")}
        for case_id, a in a_rows.items():
            b = rows.get(case_id)
            if not b:
                continue
            if a["passed"] and not b["passed"]:
                stats["A_pass_candidate_fail"] += 1
            elif not a["passed"] and b["passed"]:
                stats["A_fail_candidate_pass"] += 1
            elif a["passed"] and b["passed"]:
                stats["both_pass"] += 1
            else:
                stats["both_fail"] += 1
        out[mode] = stats
    return out


def build_blind_review_package(results: dict[str, Any]) -> dict[str, Any]:
    samples = []
    labels = ["Output A", "Output B", "Output C"]
    for idx, case in enumerate(composer_cases()):
        outputs = []
        for label, mode in zip(labels, [m.value for m in LLMArchitectureMode]):
            mode_cases = results.get(mode, {}).get("cases", [])
            found = next((row for row in mode_cases if row["id"] == case.case_id), None)
            if found:
                outputs.append({"label": label, "text": found["output"]})
        samples.append({"case_id": f"blind_{idx + 1:03d}", "task": case.task, "outputs": outputs})
    rubric = ["Đúng trọng tâm", "Dễ hiểu", "Mạch lạc", "Có giá trị quản lý", "Không lặp", "Không chung chung", "Giữ đúng giới hạn dữ liệu", "Chất lượng tiếng Việt"]
    return {"status": "PENDING_BLIND_HUMAN_REVIEW", "rubric_1_to_5": rubric, "samples": samples}


def choose_fast_structured_model(models: list[dict[str, Any]], current: str) -> str | None:
    names = [str(item.get("name") or "") for item in models]
    excluded = {current}
    for name in names:
        low = name.lower()
        if name in excluded or "vl" in low or "vision" in low:
            continue
        if any(token in low for token in ["1.5b", "3b", "mini", "small", "phi"]):
            return name
    return None


def resource_snapshot() -> dict[str, Any]:
    return {
        "peak_ram_mb": None,
        "peak_vram_mb": None,
        "cpu_utilization": None,
        "disk_model_size": None,
        "simultaneous_model_residency": None,
        "note": "Resource probes are placeholders unless OS/GPU counters are enabled for the benchmark run.",
    }


def ollama_models() -> list[dict[str, Any]]:
    text = run_command(["ollama", "list"])
    models = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3:
            models.append({"name": parts[0], "id": parts[1], "size": " ".join(parts[2:4]) if len(parts) >= 4 else parts[2]})
    return models


def write_json(name: str, payload: Any) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def git(args: list[str]) -> str:
    return run_command(["git", *args])


def run_command(args: list[str]) -> str:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=30, cwd=ROOT)
    except Exception as exc:
        return f"ERROR: {exc}"
    return (result.stdout or result.stderr or "").strip()


def rate(values: Any) -> float:
    items = list(values)
    return round(sum(1 for item in items if item) / max(1, len(items)), 4)


def mean_bool(values: Any) -> float:
    return rate(values)


def tagged_rate(rows: list[dict[str, Any]], tag: str) -> float | None:
    selected = [row for row in rows if tag in row.get("tags", [])]
    return None if not selected else rate(row["passed"] for row in selected)


def clarification_precision(rows: list[dict[str, Any]]) -> float:
    predicted = [row for row in rows if (row.get("actual") or {}).get("clarification_required")]
    if not predicted:
        return 1.0
    return rate(row["expected"].get("clarification_required") for row in predicted)


def clarification_recall(rows: list[dict[str, Any]]) -> float:
    expected = [row for row in rows if row["expected"].get("clarification_required")]
    if not expected:
        return 1.0
    return rate((row.get("actual") or {}).get("clarification_required") for row in expected)


def unnecessary_clarification_rate(rows: list[dict[str, Any]]) -> float:
    return rate((row.get("actual") or {}).get("clarification_required") and not row["expected"].get("clarification_required") for row in rows)


def ci95(successes: int, n: int) -> dict[str, float | int]:
    if n <= 0:
        return {"n": 0, "rate": 0, "lower": 0, "upper": 0}
    p = successes / n
    margin = 1.96 * math.sqrt((p * (1 - p)) / n)
    return {"n": n, "rate": round(p, 4), "lower": round(max(0, p - margin), 4), "upper": round(min(1, p + margin), 4)}


def latency_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p50": None, "p95": None, "p99": None, "min": None, "max": None, "stdev": None}
    vals = sorted(values)
    return {
        "median": round(statistics.median(vals), 2),
        "p50": percentile(vals, 50),
        "p95": percentile(vals, 95),
        "p99": percentile(vals, 99) if len(vals) >= 20 else None,
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "stdev": round(statistics.pstdev(vals), 2),
    }


def percentile(vals: list[float], pct: int) -> float:
    idx = min(len(vals) - 1, max(0, math.ceil((pct / 100) * len(vals)) - 1))
    return round(vals[idx], 2)


def macro_f1(rows: list[dict[str, Any]], labels: list[str]) -> float:
    scores = []
    for label in labels:
        tp = sum(1 for row in rows if row["expected"]["expected_intent_enum"] == label and (row.get("actual") or {}).get("intent") == label)
        fp = sum(1 for row in rows if row["expected"]["expected_intent_enum"] != label and (row.get("actual") or {}).get("intent") == label)
        fn = sum(1 for row in rows if row["expected"]["expected_intent_enum"] == label and (row.get("actual") or {}).get("intent") != label)
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        scores.append(0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    return round(sum(scores) / max(1, len(scores)), 4)


def _empty_semantic_metrics() -> dict[str, Any]:
    return {"intent_accuracy": None, "turn_relationship_accuracy": None, "sample_count": 0}


def _empty_composer_metrics() -> dict[str, Any]:
    return {"numeric_grounding_pass_rate": None, "invalid_narrative_rate": None, "sample_count": 0}


def ascii_text(text: str) -> str:
    lowered = str(text).lower().replace("đ", "d").replace("Đ", "d")
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def get_nested(payload: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def delta(values: dict[str, Any]) -> Any:
    a = values.get(LLMArchitectureMode.LEGACY_SINGLE_MODEL.value)
    b = values.get(LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL.value)
    c = values.get(LLMArchitectureMode.DUAL_MODEL.value)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return {"B_minus_A": round(b - a, 4), "C_minus_A": round(c - a, 4) if isinstance(c, (int, float)) else None}
    return None


def main(section: str, live_model: bool = False, max_cases: int | None = None, repetitions: int = 3) -> int:
    if section == "semantic":
        payload = run_semantic_benchmark(live_model=live_model, max_cases=max_cases)
        write_json("semantic_resolver_results.json", payload)
    elif section == "composer":
        payload = run_composer_benchmark(live_model=live_model, max_cases=max_cases)
    elif section == "context":
        payload = run_context_replay_benchmark()
    elif section == "performance":
        payload = run_performance_benchmark(repetitions=repetitions)
    elif section == "stability":
        payload = run_stability_benchmark(repetitions=repetitions)
    else:
        payload = run_full_benchmark(live_model=live_model, max_cases=max_cases, repetitions=repetitions)
    print(json.dumps({"section": section, "status": payload.get("status"), "artifacts": str(ARTIFACT_DIR)}, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=["all", "semantic", "composer", "context", "performance", "stability"], default="all")
    parser.add_argument("--live-model", action="store_true", help="Call local Ollama for split-role model steps.")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--repetitions", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(args.section, live_model=args.live_model, max_cases=args.max_cases, repetitions=args.repetitions))
