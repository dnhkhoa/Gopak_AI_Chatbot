from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ExecutionMode(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    REAL_LLM = "REAL_LLM"
    CLARIFICATION = "CLARIFICATION"
    REFUSAL = "REFUSAL"
    SAFE_FAILURE = "SAFE_FAILURE"
    LEGACY_FALLBACK = "LEGACY_FALLBACK"


@dataclass
class RouteDecision:
    mode: ExecutionMode
    confidence: float
    reason: str
    requires_llm: bool = False


@dataclass
class ExecutionMetadata:
    execution_mode: str
    router_confidence: float
    routing_reason: str
    llm_called: bool = False
    llm_call_count: int = 0
    fallback_used: bool = False
    fallback_reason: str | None = None
    validation_passed: bool = False
    selected_tables: list[str] = field(default_factory=list)
    selected_columns: list[str] = field(default_factory=list)
    latency_ms: dict[str, float] = field(default_factory=lambda: {
        "routing": 0.0,
        "llm": 0.0,
        "validation": 0.0,
        "query": 0.0,
        "rendering": 0.0,
        "total": 0.0,
    })
    extra: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "router_confidence": self.router_confidence,
            "routing_reason": self.routing_reason,
            "llm_called": self.llm_called,
            "llm_call_count": self.llm_call_count,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "validation_passed": self.validation_passed,
            "selected_tables": self.selected_tables,
            "selected_columns": self.selected_columns,
            "latency_ms": self.latency_ms,
            **self.extra,
        }
