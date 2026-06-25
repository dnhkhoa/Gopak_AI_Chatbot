from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from src.conversation.state import ConversationState
from src.llm.ollama_client import OllamaClient
from src.llm.semantic_contracts import (
    CanonicalizationRecord,
    ResolverTrace,
    SemanticIntent,
    SemanticResolution,
    SemanticValidationResult,
    TurnRelationship,
)


INTENT_ALIASES = {
    "DATASET OVERVIEW": SemanticIntent.DATASET_OVERVIEW,
    "OVERVIEW": SemanticIntent.DATASET_OVERVIEW,
    "AGGREGATION": SemanticIntent.AGGREGATION,
    "SUM": SemanticIntent.AGGREGATION,
    "COUNT": SemanticIntent.AGGREGATION,
    "RANKING": SemanticIntent.RANKING,
    "TOP_N": SemanticIntent.RANKING,
    "TOP N": SemanticIntent.RANKING,
    "TIME TREND": SemanticIntent.TIME_TREND,
    "TIME_TREND": SemanticIntent.TIME_TREND,
    "TREND": SemanticIntent.TIME_TREND,
    "DISTRIBUTION": SemanticIntent.DISTRIBUTION,
    "COMPARISON": SemanticIntent.COMPARISON,
    "RECORD LOOKUP": SemanticIntent.RECORD_LOOKUP,
    "CHART": SemanticIntent.CHART_CREATE,
    "CHART CREATE": SemanticIntent.CHART_CREATE,
    "CHART_CREATE": SemanticIntent.CHART_CREATE,
    "CHART REVISION": SemanticIntent.CHART_REVISION,
    "REPORT": SemanticIntent.REPORT_CREATE,
    "REPORT CREATE": SemanticIntent.REPORT_CREATE,
    "REPORT_CREATE": SemanticIntent.REPORT_CREATE,
    "REPORT REVISION": SemanticIntent.REPORT_REVISION,
    "REPORT_REVISION": SemanticIntent.REPORT_REVISION,
    "REPORT EXPORT": SemanticIntent.REPORT_EXPORT,
    "REPORT_EXPORT": SemanticIntent.REPORT_EXPORT,
    "ARTIFACT QUESTION": SemanticIntent.ARTIFACT_QUESTION,
    "CLARIFICATION ANSWER": SemanticIntent.CLARIFICATION_ANSWER,
    "CORRECTION": SemanticIntent.CORRECTION,
    "CANCEL": SemanticIntent.CANCEL,
    "UNSUPPORTED": SemanticIntent.UNSUPPORTED_REQUEST,
}

RELATIONSHIP_ALIASES = {
    "NEW REQUEST": TurnRelationship.NEW_REQUEST,
    "NEW_REQUEST": TurnRelationship.NEW_REQUEST,
    "FOLLOW UP": TurnRelationship.FOLLOW_UP_QUESTION,
    "FOLLOW_UP": TurnRelationship.FOLLOW_UP_QUESTION,
    "FOLLOW UP QUESTION": TurnRelationship.FOLLOW_UP_QUESTION,
    "FOLLOW_UP_QUESTION": TurnRelationship.FOLLOW_UP_QUESTION,
    "ARTIFACT REVISION": TurnRelationship.ARTIFACT_REVISION,
    "ARTIFACT_REVISION": TurnRelationship.ARTIFACT_REVISION,
    "REPORT REVISION": TurnRelationship.ARTIFACT_REVISION,
    "ARTIFACT EXPORT": TurnRelationship.ARTIFACT_EXPORT,
    "ARTIFACT_EXPORT": TurnRelationship.ARTIFACT_EXPORT,
    "REPORT EXPORT": TurnRelationship.ARTIFACT_EXPORT,
    "CLARIFICATION ANSWER": TurnRelationship.CLARIFICATION_ANSWER,
    "CLARIFICATION_ANSWER": TurnRelationship.CLARIFICATION_ANSWER,
    "CORRECTION": TurnRelationship.CORRECTION,
    "CANCEL": TurnRelationship.CANCEL,
    "AMBIGUOUS": TurnRelationship.AMBIGUOUS,
}


@dataclass(frozen=True)
class SemanticResolverInput:
    raw_text: str
    normalized_text: str
    conversation_state_summary: dict[str, Any]
    last_visible_artifact_summary: dict[str, Any]
    pending_clarification_summary: dict[str, Any] | None
    available_dataset_capabilities: dict[str, Any]
    available_semantic_fields: list[str]


@dataclass(frozen=True)
class SemanticResolverResult:
    resolution: SemanticResolution | None
    trace: ResolverTrace


def normalize_for_lookup(text: str) -> str:
    lowered = str(text).lower().replace("đ", "d").replace("Đ", "d")
    normalized = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def build_resolver_input(message: str, state: ConversationState, capabilities: dict[str, Any] | None = None) -> SemanticResolverInput:
    pending = state.pending_clarification.model_dump(mode="json") if state.pending_clarification else None
    report = state.active_report_context.model_dump(mode="json") if state.active_report_context else None
    return SemanticResolverInput(
        raw_text=message,
        normalized_text=normalize_for_lookup(message),
        conversation_state_summary={
            "active_file_id": state.active_file_id,
            "active_file_name": state.active_file_name,
            "has_previous_result": bool(state.last_result_summary),
            "active_report_context": report,
        },
        last_visible_artifact_summary={
            "artifact_id": state.last_visible_artifact_id,
            "artifact_type": state.last_visible_artifact_type,
        },
        pending_clarification_summary=pending,
        available_dataset_capabilities=capabilities or {},
        available_semantic_fields=list((capabilities or {}).get("fields") or []),
    )


class SemanticResolver:
    def __init__(self, client: OllamaClient | None, model_name: str | None, architecture_mode: str) -> None:
        self.client = client
        self.model_name = model_name
        self.architecture_mode = architecture_mode

    def resolve(self, resolver_input: SemanticResolverInput) -> SemanticResolverResult:
        trace = ResolverTrace(
            architecture_mode=self.architecture_mode,
            resolver_model=self.model_name,
            resolver_started=True,
        )
        start = time.perf_counter()
        if self.client is None:
            trace.failure_classification.append("MODEL_UNAVAILABLE")
            trace.latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return SemanticResolverResult(None, trace)

        messages = self._messages(resolver_input)
        raw = None
        for attempt in range(2):
            if attempt:
                trace.resolver_retry_count += 1
                messages = self._retry_messages(resolver_input, raw or "", trace.failure_classification)
            try:
                response = self.client.chat(messages, format_schema=SemanticResolution.model_json_schema())
                raw = response.text
                trace.raw_response = raw if attempt == 0 else trace.raw_response
                if attempt == 1:
                    trace.repaired_response = raw
                resolution, parse_trace = parse_semantic_resolution(raw)
                trace.canonicalization.extend(parse_trace.canonicalization)
                trace.strict_parse_valid = parse_trace.strict_parse_valid
                trace.canonicalized_parse_valid = parse_trace.canonicalized_parse_valid
                trace.resolver_schema_valid = resolution is not None
                trace.resolver_enum_valid = resolution is not None
                if resolution is None:
                    trace.failure_classification.extend(parse_trace.failure_classification)
                    continue
                validation = validate_semantic_resolution(resolution, resolver_input)
                trace.semantic_validation = validation
                if validation.passed:
                    trace.resolver_completed = True
                    trace.latency_ms = round((time.perf_counter() - start) * 1000, 2)
                    return SemanticResolverResult(resolution, trace)
                trace.failure_classification.extend(validation.failure_classification)
            except Exception as exc:
                trace.failure_classification.append("TIMEOUT" if "timeout" in str(exc).lower() else "ENVIRONMENT_FAILED")
        trace.resolver_completed = False
        trace.latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return SemanticResolverResult(None, trace)

    def _messages(self, resolver_input: SemanticResolverInput) -> list[dict[str, str]]:
        payload = {
            "raw_user_message": resolver_input.raw_text,
            "conversation_state_summary": resolver_input.conversation_state_summary,
            "last_visible_artifact_summary": resolver_input.last_visible_artifact_summary,
            "pending_clarification_summary": resolver_input.pending_clarification_summary,
            "available_dataset_capabilities": resolver_input.available_dataset_capabilities,
            "available_semantic_fields": resolver_input.available_semantic_fields,
            "allowed_intents": [item.value for item in SemanticIntent],
            "allowed_turn_relationships": [item.value for item in TurnRelationship],
        }
        return [
            {
                "role": "system",
                "content": (
                    "Resolve Vietnamese analytics requests into the provided enum taxonomy. "
                    "Return only JSON matching the schema. Do not answer the user, do not explain, "
                    "do not generate SQL, and do not calculate numbers."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]

    def _retry_messages(self, resolver_input: SemanticResolverInput, raw: str, errors: list[str]) -> list[dict[str, str]]:
        payload = {
            "validation_error": errors[-5:],
            "raw_invalid_response": raw[:4000],
            "schema": SemanticResolution.model_json_schema(),
            "instruction": "Fix structure and enum values only. Do not reinterpret the request.",
            "original_input": {
                "raw_user_message": resolver_input.raw_text,
                "conversation_state_summary": resolver_input.conversation_state_summary,
            },
        }
        return [
            {"role": "system", "content": "Return only valid JSON for the schema. No prose."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]


def parse_semantic_resolution(raw: str) -> tuple[SemanticResolution | None, ResolverTrace]:
    trace = ResolverTrace(architecture_mode="parser")
    try:
        resolution = SemanticResolution.model_validate_json(raw)
        trace.strict_parse_valid = True
        trace.resolver_schema_valid = True
        trace.resolver_enum_valid = True
        return resolution, trace
    except ValidationError as exc:
        trace.failure_classification.append(_validation_failure_classification(exc))
    except Exception:
        trace.failure_classification.append("INVALID_JSON")
        return None, trace

    try:
        payload = json.loads(raw)
    except Exception:
        trace.failure_classification.append("INVALID_JSON")
        return None, trace
    payload, records = canonicalize_semantic_payload(payload)
    trace.canonicalization.extend(records)
    try:
        resolution = SemanticResolution.model_validate(payload)
        trace.canonicalized_parse_valid = True
        trace.resolver_schema_valid = True
        trace.resolver_enum_valid = True
        return resolution, trace
    except ValidationError as exc:
        trace.failure_classification.append(_validation_failure_classification(exc))
        return None, trace


def canonicalize_semantic_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[CanonicalizationRecord]]:
    copied = dict(payload)
    records: list[CanonicalizationRecord] = []
    for field, aliases in [("intent", INTENT_ALIASES), ("turn_relationship", RELATIONSHIP_ALIASES)]:
        raw = copied.get(field)
        if raw is None:
            continue
        if raw in [item.value for item in (SemanticIntent if field == "intent" else TurnRelationship)]:
            continue
        key = _alias_key(str(raw))
        canonical = aliases.get(key)
        accepted = canonical is not None
        copied[field] = canonical.value if canonical else raw
        records.append(
            CanonicalizationRecord(
                raw_value=str(raw),
                canonical_value=canonical.value if canonical else None,
                canonicalization_rule=f"{field}_static_alias" if canonical else None,
                accepted=accepted,
                classification="TAXONOMY_FORMAT_ONLY" if accepted else "ENUM_VALIDATION_FAILED",
            )
        )
    return copied, records


def validate_semantic_resolution(resolution: SemanticResolution, resolver_input: SemanticResolverInput) -> SemanticValidationResult:
    errors: list[str] = []
    classes: list[str] = []
    fields = set(resolver_input.available_semantic_fields or [])

    if resolution.intent == SemanticIntent.REPORT_EXPORT:
        if resolution.turn_relationship != TurnRelationship.ARTIFACT_EXPORT:
            errors.append("REPORT_EXPORT must use ARTIFACT_EXPORT relationship")
            classes.append("TURN_RELATIONSHIP_WRONG")
        if not resolver_input.conversation_state_summary.get("active_report_context"):
            errors.append("REPORT_EXPORT requires active report context")
            classes.append("ARTIFACT_REFERENCE_WRONG")
        if resolution.clarification_required:
            errors.append("REPORT_EXPORT must not ask for metric or dimension clarification")
            classes.append("UNNECESSARY_CLARIFICATION")

    if resolution.intent == SemanticIntent.REPORT_REVISION:
        if resolution.turn_relationship != TurnRelationship.ARTIFACT_REVISION:
            errors.append("REPORT_REVISION must use ARTIFACT_REVISION relationship")
            classes.append("TURN_RELATIONSHIP_WRONG")
        if resolution.clarification_required:
            errors.append("REPORT_REVISION must not ask for metric or dimension clarification")
            classes.append("UNNECESSARY_CLARIFICATION")

    if resolution.intent == SemanticIntent.TIME_TREND and not (resolution.time_grain or "date" in resolution.dimensions):
        errors.append("TIME_TREND requires date dimension or time_grain")
        classes.append("FIELD_MAPPING_WRONG")

    if resolution.intent == SemanticIntent.RANKING and not (resolution.metrics and resolution.dimensions):
        errors.append("RANKING requires metric and dimension")
        classes.append("FIELD_MAPPING_WRONG")

    if resolution.clarification_required and _complete_enough(resolution):
        errors.append("clarification_required is true although request has enough slots")
        classes.append("UNNECESSARY_CLARIFICATION")

    unknown_fields = [item for item in resolution.dimensions + resolution.metrics if fields and item not in fields and item not in _GENERIC_FIELDS]
    if unknown_fields:
        errors.append(f"unknown semantic fields: {unknown_fields}")
        classes.append("FIELD_MAPPING_WRONG")

    return SemanticValidationResult(passed=not errors, errors=errors, failure_classification=sorted(set(classes)))


def _validation_failure_classification(exc: ValidationError) -> str:
    for error in exc.errors():
        location = error.get("loc") or ()
        if location and location[-1] in {"intent", "turn_relationship"}:
            return "ENUM_VALIDATION_FAILED"
    text = str(exc)
    if "Input should be" in text and ("SemanticIntent" in text or "TurnRelationship" in text):
        return "ENUM_VALIDATION_FAILED"
    if "Extra inputs are not permitted" in text:
        return "SCHEMA_VALIDATION_FAILED"
    return "SCHEMA_VALIDATION_FAILED"


def _complete_enough(resolution: SemanticResolution) -> bool:
    if resolution.intent in {SemanticIntent.REPORT_EXPORT, SemanticIntent.REPORT_REVISION, SemanticIntent.ARTIFACT_QUESTION}:
        return True
    if resolution.intent in {SemanticIntent.RANKING, SemanticIntent.TIME_TREND, SemanticIntent.DISTRIBUTION}:
        return bool(resolution.metrics or resolution.intent == SemanticIntent.DISTRIBUTION) and bool(resolution.dimensions or resolution.time_grain)
    return bool(resolution.intent)


def _alias_key(value: str) -> str:
    normalized = normalize_for_lookup(value)
    return re.sub(r"[\s\-]+", "_", normalized).upper().replace("__", "_").replace("_", " ")


_GENERIC_FIELDS = {
    "machine",
    "cause",
    "loss_name",
    "loss_group",
    "date",
    "total_downtime",
    "count",
    "average_duration",
    "transaction_value",
}
