from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


PipelineState = Literal[
    "RECEIVED",
    "CONTEXT_RESOLVED",
    "SOURCE_ROUTED",
    "PLAN_CREATED",
    "PLAN_VALIDATED",
    "EXECUTION_PREPARED",
    "EXECUTED",
    "RESULT_VALIDATED",
    "RENDERED",
    "COMPLETED",
    "CLARIFICATION_REQUIRED",
    "OUT_OF_SCOPE",
    "SOURCE_UNAVAILABLE",
    "PLAN_REJECTED",
    "EXECUTION_REJECTED",
    "EXECUTION_FAILED",
    "RESULT_REJECTED",
    "SAFE_FAILURE",
]


class ExecutionPlan(BaseModel):
    source_id: str
    operation: Literal[
        "apqoee_as_of",
        "apqoee_trend",
        "apqoee_period_unsupported",
        "downtime_interval",
        "loss_interval",
    ]
    metric_scope: list[str] = Field(default_factory=list)
    time_scope: dict[str, Any] = Field(default_factory=dict)
    grain: str

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        allowed = {"machine_downtime", "loss_assignment", "apqoee_cumulative"}
        if value not in allowed:
            raise ValueError(f"Unsupported source_id: {value}")
        return value


class EvidencePack(BaseModel):
    status: Literal["ok", "clarification", "not_answerable", "rejected", "failed"]
    state: PipelineState
    sources_used: list[str] = Field(default_factory=list)
    time_scope: dict[str, Any] = Field(default_factory=dict)
    metric_scope: list[str] = Field(default_factory=list)
    data_version: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    route: dict[str, Any] = Field(default_factory=dict)
    execution_plans: list[dict[str, Any]] = Field(default_factory=list)

