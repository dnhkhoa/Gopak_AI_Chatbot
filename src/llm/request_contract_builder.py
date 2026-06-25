from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.application.turn_contracts import RequestContract
from src.conversation.state import ConversationState
from src.llm.semantic_contracts import SemanticIntent, SemanticResolution, TurnRelationship


@dataclass(frozen=True)
class RequestContractBuildResult:
    contract: RequestContract | None
    valid: bool
    errors: list[str] = field(default_factory=list)
    failure_classification: list[str] = field(default_factory=list)


class RequestContractBuilder:
    def build(
        self,
        semantic_resolution: SemanticResolution,
        conversation_state: ConversationState,
        dataset_capabilities: dict[str, Any] | None = None,
        artifact_context: dict[str, Any] | None = None,
    ) -> RequestContractBuildResult:
        capabilities = dataset_capabilities or {}
        allowed_fields = set(capabilities.get("fields") or [])
        errors: list[str] = []
        classes: list[str] = []

        unknown = [
            item
            for item in semantic_resolution.dimensions + semantic_resolution.metrics
            if allowed_fields and item not in allowed_fields and item not in _CANONICAL_FIELD_ALIASES
        ]
        if unknown:
            errors.append(f"Unknown semantic fields: {unknown}")
            classes.append("FIELD_MAPPING_WRONG")

        required = set(_required_capabilities(semantic_resolution))
        available = set(capabilities.get("capabilities") or [])
        if required and available and not required.issubset(available):
            errors.append(f"Required capabilities not available: {sorted(required - available)}")
            classes.append("CAPABILITY_VALIDATION_FAILED")

        if semantic_resolution.intent == SemanticIntent.REPORT_EXPORT and not conversation_state.active_report_context:
            errors.append("REPORT_EXPORT requires active report context")
            classes.append("ARTIFACT_REFERENCE_WRONG")

        if semantic_resolution.clarification_required and semantic_resolution.turn_relationship in {
            TurnRelationship.ARTIFACT_EXPORT,
            TurnRelationship.ARTIFACT_REVISION,
            TurnRelationship.FOLLOW_UP_QUESTION,
        }:
            errors.append("Clarification is not allowed for clear artifact action")
            classes.append("UNNECESSARY_CLARIFICATION")

        if errors:
            return RequestContractBuildResult(None, False, errors, sorted(set(classes)))

        relation = _relation_to_contract(semantic_resolution.turn_relationship)
        inherited_fields: list[str] = []
        reset_fields: list[str] = []
        if semantic_resolution.turn_relationship == TurnRelationship.NEW_REQUEST:
            reset_fields = ["dimension", "metric", "filter", "time_range", "chart_type", "top_n", "pending_clarification"]
        elif semantic_resolution.turn_relationship == TurnRelationship.FOLLOW_UP_QUESTION:
            inherited_fields = ["referenced_artifact_payload"]
        elif semantic_resolution.turn_relationship in {TurnRelationship.ARTIFACT_EXPORT, TurnRelationship.ARTIFACT_REVISION}:
            inherited_fields = ["active_report_context", "validated_report_payload", "source_file"]

        contract = RequestContract(
            relation_to_previous_turn=relation,
            intent=_contract_intent(semantic_resolution.intent),
            source_file_id=conversation_state.active_file_id,
            dimensions=[_canonical_field(item) for item in semantic_resolution.dimensions],
            metrics=[_canonical_field(item) for item in semantic_resolution.metrics],
            aggregations=list(semantic_resolution.aggregations),
            filters=[flt.model_dump(mode="json") for flt in semantic_resolution.filters],
            time_range=semantic_resolution.time_range,
            time_grain=semantic_resolution.time_grain,
            ranking=semantic_resolution.ranking,
            limit=semantic_resolution.limit,
            requested_outputs=list(semantic_resolution.requested_outputs),
            requested_chart_type=semantic_resolution.requested_chart_type,
            report_type="downtime" if semantic_resolution.intent in _REPORT_INTENTS else None,
            report_detail_level=semantic_resolution.requested_report_detail,
            inherited_fields=inherited_fields,
            explicitly_reset_fields=reset_fields,
        )
        return RequestContractBuildResult(contract, True)


def _relation_to_contract(relationship: TurnRelationship) -> str:
    if relationship == TurnRelationship.FOLLOW_UP_QUESTION:
        return "FOLLOW_UP_ON_PREVIOUS_RESULT"
    if relationship in {TurnRelationship.ARTIFACT_REVISION, TurnRelationship.ARTIFACT_EXPORT, TurnRelationship.CORRECTION}:
        return "REFINEMENT"
    return "NEW_REQUEST"


def _contract_intent(intent: SemanticIntent) -> str:
    if intent in _REPORT_INTENTS:
        return "report"
    if intent in {SemanticIntent.CHART_CREATE, SemanticIntent.CHART_REVISION, SemanticIntent.TIME_TREND, SemanticIntent.DISTRIBUTION}:
        return "chart"
    if intent == SemanticIntent.ARTIFACT_QUESTION:
        return "commentary"
    if intent == SemanticIntent.UNSUPPORTED_REQUEST:
        return "refusal"
    return "query"


def _required_capabilities(resolution: SemanticResolution) -> list[str]:
    required = []
    if any(metric in {"total_downtime", "average_duration"} for metric in resolution.metrics):
        required.append("downtime")
    if any(metric == "transaction_value" for metric in resolution.metrics):
        required.append("transaction_value")
    if resolution.intent in _REPORT_INTENTS:
        required.append("report")
    return required


def _canonical_field(field: str) -> str:
    return _CANONICAL_FIELD_ALIASES.get(field, field)


_REPORT_INTENTS = {
    SemanticIntent.REPORT_CREATE,
    SemanticIntent.REPORT_REVISION,
    SemanticIntent.REPORT_EXPORT,
    SemanticIntent.REPORT_QUESTION,
}

_CANONICAL_FIELD_ALIASES = {
    "cause": "loss_name",
    "downtime_duration": "total_downtime",
    "event_count": "count",
}
