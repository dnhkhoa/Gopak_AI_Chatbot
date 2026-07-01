from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Literal

from src.sources.registry import ProductionSource


RouteStatus = Literal["answerable", "clarification", "not_answerable"]
ExecutionStrategy = Literal["single_source", "validated_join", "parallel_queries_then_merge", "clarification", "not_answerable"]


@dataclass(frozen=True)
class SourceRoute:
    status: RouteStatus
    source_ids: tuple[str, ...]
    source_roles: dict[str, str]
    execution_strategy: ExecutionStrategy
    requested_metrics: tuple[str, ...]
    requested_grain: str
    time_semantics: str
    confidence: float
    clarification_question: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source_ids": list(self.source_ids),
            "source_roles": self.source_roles,
            "execution_strategy": self.execution_strategy,
            "requested_metrics": list(self.requested_metrics),
            "requested_grain": self.requested_grain,
            "time_semantics": self.time_semantics,
            "confidence": self.confidence,
            "clarification_question": self.clarification_question,
        }


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower().replace("đ", "d").replace("Đ", "d"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


class SourceRouter:
    def __init__(self, sources: list[ProductionSource]):
        self.sources = {source.source_id: source for source in sources}

    def route(self, question: str, conversation_context: dict | None = None) -> SourceRoute:
        text = normalize_text(question)
        source_ids: list[str] = []
        metrics: list[str] = []

        if self._has_any(text, ["oee", "apqoee", "availability", "performance", "quality", "counter", "san luong", "hieu suat"]):
            source_ids.append("apqoee_cumulative")
            metrics.append("oee" if "oee" in text else "production_efficiency")
        if self._has_any(text, ["downtime", "dung may", "dung", "thoi luong dung", "may bi anh huong"]):
            source_ids.append("machine_downtime")
            metrics.append("downtime_duration")
        if self._has_any(text, ["loss", "ton that", "nhom ton that", "phan bo", "nguyen nhan"]):
            source_ids.append("loss_assignment")
            metrics.append("loss_duration")

        source_ids = [sid for sid in dict.fromkeys(source_ids) if sid in self.sources]
        if not source_ids:
            return SourceRoute(
                status="clarification",
                source_ids=(),
                source_roles={},
                execution_strategy="clarification",
                requested_metrics=(),
                requested_grain="unknown",
                time_semantics="unknown",
                confidence=0.0,
                clarification_question="Please specify whether you want OEE, machine downtime, loss assignment, or a comparison across those sources.",
            )

        unavailable = [sid for sid in source_ids if self.sources[sid].status != "ready"]
        if unavailable:
            return SourceRoute(
                status="not_answerable",
                source_ids=tuple(source_ids),
                source_roles={sid: "primary" if index == 0 else "supporting" for index, sid in enumerate(source_ids)},
                execution_strategy="not_answerable",
                requested_metrics=tuple(dict.fromkeys(metrics)),
                requested_grain=self._grain(text),
                time_semantics=self._time_semantics(text),
                confidence=0.95,
                clarification_question=f"Source unavailable: {', '.join(unavailable)}.",
            )

        strategy: ExecutionStrategy = "single_source" if len(source_ids) == 1 else "parallel_queries_then_merge"
        return SourceRoute(
            status="answerable",
            source_ids=tuple(source_ids),
            source_roles={sid: "primary" if index == 0 else "supporting" for index, sid in enumerate(source_ids)},
            execution_strategy=strategy,
            requested_metrics=tuple(dict.fromkeys(metrics)),
            requested_grain=self._grain(text),
            time_semantics=self._time_semantics(text),
            confidence=0.98 if len(source_ids) == 1 else 0.95,
        )

    def _has_any(self, text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)

    def _grain(self, text: str) -> str:
        if self._has_any(text, ["rieng ngay", "trong ngay", "ngay"]):
            return "day"
        if self._has_any(text, ["thang", "month"]):
            return "month"
        if self._has_any(text, ["xu huong", "trend"]):
            return "trend"
        if self._has_any(text, ["tai ", "den ngay", "as of", "den "]):
            return "cumulative_as_of"
        return "summary"

    def _time_semantics(self, text: str) -> str:
        if self._has_any(text, ["rieng ngay", "trong ngay", "period", "khoang", "tu "]):
            return "period"
        if self._has_any(text, ["xu huong", "trend"]):
            return "trend"
        if self._has_any(text, ["den ngay", "tai ", "as of", "den "]):
            return "as_of"
        return "summary"
