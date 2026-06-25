from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SemanticIntent(StrEnum):
    DATASET_OVERVIEW = "DATASET_OVERVIEW"
    AGGREGATION = "AGGREGATION"
    RANKING = "RANKING"
    TIME_TREND = "TIME_TREND"
    DISTRIBUTION = "DISTRIBUTION"
    COMPARISON = "COMPARISON"
    RECORD_LOOKUP = "RECORD_LOOKUP"
    CHART_CREATE = "CHART_CREATE"
    CHART_REVISION = "CHART_REVISION"
    REPORT_CREATE = "REPORT_CREATE"
    REPORT_REVISION = "REPORT_REVISION"
    REPORT_EXPORT = "REPORT_EXPORT"
    REPORT_QUESTION = "REPORT_QUESTION"
    ARTIFACT_QUESTION = "ARTIFACT_QUESTION"
    CLARIFICATION_ANSWER = "CLARIFICATION_ANSWER"
    CORRECTION = "CORRECTION"
    CANCEL = "CANCEL"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"


class TurnRelationship(StrEnum):
    NEW_REQUEST = "NEW_REQUEST"
    FOLLOW_UP_QUESTION = "FOLLOW_UP_QUESTION"
    ARTIFACT_REVISION = "ARTIFACT_REVISION"
    ARTIFACT_EXPORT = "ARTIFACT_EXPORT"
    CLARIFICATION_ANSWER = "CLARIFICATION_ANSWER"
    CORRECTION = "CORRECTION"
    CANCEL = "CANCEL"
    AMBIGUOUS = "AMBIGUOUS"


class SemanticFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: str
    value: Any


class SemanticResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "semantic_resolution.v1"
    intent: SemanticIntent
    turn_relationship: TurnRelationship
    referenced_artifact_id: str | None = None
    referenced_artifact_type: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    aggregations: list[str] = Field(default_factory=list)
    filters: list[SemanticFilter] = Field(default_factory=list)
    time_range: dict[str, Any] | None = None
    time_grain: str | None = None
    ranking: str | None = None
    limit: int | None = None
    requested_outputs: list[str] = Field(default_factory=list)
    requested_chart_type: str | None = None
    requested_report_action: str | None = None
    requested_report_detail: str | None = None
    clarification_required: bool = False
    clarification_slots: list[str] = Field(default_factory=list)
    clarification_reason: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CanonicalizationRecord(BaseModel):
    raw_value: str
    canonical_value: str | None
    canonicalization_rule: str | None
    accepted: bool
    classification: str | None = None


class SemanticValidationResult(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)
    failure_classification: list[str] = Field(default_factory=list)


class ResolverTrace(BaseModel):
    architecture_mode: str
    resolver_model: str | None = None
    resolver_started: bool = False
    resolver_completed: bool = False
    resolver_retry_count: int = 0
    resolver_schema_valid: bool = False
    resolver_enum_valid: bool = False
    strict_parse_valid: bool = False
    canonicalized_parse_valid: bool = False
    canonicalization: list[CanonicalizationRecord] = Field(default_factory=list)
    semantic_validation: SemanticValidationResult | None = None
    raw_response: str | None = None
    repaired_response: str | None = None
    failure_classification: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
