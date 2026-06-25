"""Active-file capability contract and gate (P0-B).

Three pieces, all domain-agnostic (no hardcoded UAT prompts):

  RequestRequirements        - what a question needs (concepts, not columns)
  DatasetCapabilityProfile   - what a Ready file offers (derived from semantic roles)
  ActiveFileCapabilityGate   - the single place that decides supported / unsupported

Concepts are an intermediate vocabulary so a question ("Máy nào có downtime cao
nhất?") and a file (Machine_Downtime) are compared on meaning, not phrasing.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.query_understanding.text import normalize_text
from src.rendering.labels import display_label


# Concepts that are specific enough that their absence should BLOCK a request.
# Generic concepts (count, event_time) are satisfiable by almost any file and
# must never produce a false "unsupported".
DOMAIN_SPECIFIC_DIMENSIONS = {"machine", "loss_group", "loss_name", "loss_type"}
DOMAIN_SPECIFIC_METRICS = {"downtime_duration"}


class RequestRequirements(BaseModel):
    required_dimensions: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    required_datetime_roles: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)


class DatasetCapabilityProfile(BaseModel):
    source_file_id: str
    source_file_name: str
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    datetime_roles: list[str] = Field(default_factory=list)
    supported_analyses: list[str] = Field(default_factory=list)
    domain: str = "generic_tabular"
    confidence: float = 0.5


class CapabilityResult(BaseModel):
    supported: bool
    missing_dimensions: list[str] = Field(default_factory=list)
    missing_metrics: list[str] = Field(default_factory=list)
    missing_datetime_roles: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    active_file_id: str | None = None
    active_file_name: str | None = None
    recommended_file_id: str | None = None
    recommended_file_name: str | None = None


# --- request requirements ----------------------------------------------------

def build_request_requirements(message: str) -> RequestRequirements:
    q = normalize_text(message)
    dims: list[str] = []
    metrics: list[str] = []
    datetime_roles: list[str] = []
    caps: list[str] = []

    # dimensions
    if _has(q, ["may", "machine", "thiet bi", "day chuyen"]):
        dims.append("machine")
    if _has(q, ["nhom ton that", "nhom loi"]):
        dims.append("loss_group")
    if _has(q, ["nguyen nhan", "ten ton that", "ly do dung"]):
        dims.append("loss_name")
    if _has(q, ["loai ton that"]):
        dims.append("loss_type")

    # metrics
    if _has(q, ["downtime", "dung may", "thoi gian dung", "thoi gian downtime", "tong downtime"]):
        metrics.append("downtime_duration")

    # datetime / time-series
    if _has(q, ["xu huong", "theo thoi gian", "qua thoi gian", "theo ngay", "theo thang", "theo tuan", "trend"]):
        datetime_roles.append("event_time")
        caps.append("time_series")

    # ranked aggregation
    if _has(q, ["cao nhat", "nhieu nhat", "lon nhat", "thap nhat", "it nhat", "top", "xep hang", "nao co"]):
        caps.append("ranked_aggregation")

    return RequestRequirements(
        required_dimensions=_dedupe(dims),
        required_metrics=_dedupe(metrics),
        required_datetime_roles=_dedupe(datetime_roles),
        required_capabilities=_dedupe(caps),
    )


# --- dataset capability profile ----------------------------------------------

_ROLE_DIMENSION = {
    "machine": "machine",
    "loss_name": "loss_name",
    "loss_group": "loss_group",
    "loss_type": "loss_type",
}
_DURATION_ROLES = {"duration", "duration_seconds", "duration_reported_seconds", "duration_calculated_seconds"}


def build_dataset_capability_profile(catalog: dict, file_id: str, file_name: str = "") -> DatasetCapabilityProfile:
    tables = catalog.get("tables", [])
    dims: list[str] = []
    metrics: list[str] = []
    datetime_roles: list[str] = []
    name = file_name
    for table in tables:
        if not name:
            name = str(table.get("source_file") or "")
        for col in table.get("columns", []):
            role = str(col.get("semantic_role") or "")
            normalized = str(col.get("normalized_name") or "")
            dtype = str(col.get("dtype") or "")
            if normalized.startswith("_"):
                continue  # provenance / internal columns
            # dimensions
            if role in _ROLE_DIMENSION:
                dims.append(_ROLE_DIMENSION[role])
            elif dtype.startswith("object") and 0 < int(col.get("cardinality") or 0) <= 50:
                dims.append(normalized)
            # duration metric
            if role in _DURATION_ROLES:
                metrics.append("downtime_duration")
            # numeric metrics
            if dtype.startswith(("int", "float")) and role not in {"record_no"}:
                metrics.append(normalized)
            # datetime
            if dtype.startswith("datetime") or role in {"start_time", "end_time"}:
                datetime_roles.append("event_time")
    metrics.append("count")
    dims = _dedupe(dims)
    metrics = _dedupe(metrics)
    datetime_roles = _dedupe(datetime_roles)

    domain = _infer_domain(dims, metrics)
    supported = ["aggregation", "distribution"]
    if dims and (metrics or True):
        supported.append("ranked_aggregation")
    if datetime_roles:
        supported.append("time_series")
    return DatasetCapabilityProfile(
        source_file_id=file_id,
        source_file_name=name,
        dimensions=dims,
        metrics=metrics,
        datetime_roles=datetime_roles,
        supported_analyses=_dedupe(supported),
        domain=domain,
        confidence=0.8 if domain != "generic_tabular" else 0.5,
    )


def _infer_domain(dims: list[str], metrics: list[str]) -> str:
    if "machine" in dims and "downtime_duration" in metrics:
        return "machine_downtime"
    if {"loss_group", "loss_name"} & set(dims):
        return "loss_assignment"
    return "generic_tabular"


# --- the gate ----------------------------------------------------------------

class ActiveFileCapabilityGate:
    def __init__(self, profiles: dict[str, DatasetCapabilityProfile] | None = None) -> None:
        # other Ready files' profiles, keyed by file_id, used to recommend a file
        self.other_profiles = profiles or {}

    def evaluate(self, requirements: RequestRequirements, profile: DatasetCapabilityProfile) -> CapabilityResult:
        missing_dims = [d for d in requirements.required_dimensions if d not in profile.dimensions]
        missing_metrics = [m for m in requirements.required_metrics if m not in profile.metrics]
        missing_dt = [r for r in requirements.required_datetime_roles if r not in profile.datetime_roles]
        missing_caps = [c for c in requirements.required_capabilities if c not in profile.supported_analyses]

        # Only domain-specific gaps block; generic gaps never produce "unsupported".
        blocking_dims = [d for d in missing_dims if d in DOMAIN_SPECIFIC_DIMENSIONS]
        blocking_metrics = [m for m in missing_metrics if m in DOMAIN_SPECIFIC_METRICS]
        supported = not (blocking_dims or blocking_metrics)

        result = CapabilityResult(
            supported=supported,
            missing_dimensions=missing_dims,
            missing_metrics=missing_metrics,
            missing_datetime_roles=missing_dt,
            missing_capabilities=missing_caps,
            active_file_id=profile.source_file_id,
            active_file_name=profile.source_file_name,
        )
        if not supported:
            rec = self._recommend(requirements)
            if rec:
                result.recommended_file_id = rec.source_file_id
                result.recommended_file_name = rec.source_file_name
        return result

    def _recommend(self, requirements: RequestRequirements) -> DatasetCapabilityProfile | None:
        candidates = []
        for profile in self.other_profiles.values():
            dims_ok = all(d in profile.dimensions for d in requirements.required_dimensions)
            metrics_ok = all(m in profile.metrics for m in requirements.required_metrics)
            if dims_ok and metrics_ok and (requirements.required_dimensions or requirements.required_metrics):
                candidates.append(profile)
        if not candidates:
            return None
        # Prefer the file whose name best matches the requested concepts (e.g. a
        # downtime question -> a file named "...Downtime..."), then by confidence.
        concept_terms = set()
        if "downtime_duration" in requirements.required_metrics or "machine" in requirements.required_dimensions:
            concept_terms.update({"downtime", "machine"})
        if {"loss_group", "loss_name", "loss_type"} & set(requirements.required_dimensions):
            concept_terms.update({"loss", "ton_that"})

        def score(profile: DatasetCapabilityProfile) -> tuple[int, float]:
            name = (profile.source_file_name or "").lower()
            name_hits = sum(1 for term in concept_terms if term in name)
            return (name_hits, profile.confidence)

        return max(candidates, key=score)


def unsupported_message(result: CapabilityResult) -> str:
    """Vietnamese customer message for an unsupported active-file request."""
    missing_labels: list[str] = []
    for dim in result.missing_dimensions:
        if dim in DOMAIN_SPECIFIC_DIMENSIONS:
            missing_labels.append(display_label(dim).lower())
    for metric in result.missing_metrics:
        if metric in DOMAIN_SPECIFIC_METRICS:
            missing_labels.append(display_label(metric).lower())
    missing_text = " và ".join(_dedupe(missing_labels)) or "dữ liệu cần thiết"
    base = f"File hiện tại không chứa {missing_text} để thực hiện yêu cầu này."
    if result.recommended_file_name:
        return (
            f"{base} File “{result.recommended_file_name}” phù hợp với yêu cầu này. "
            "Hãy chọn file đó để tạo một cuộc trò chuyện mới rồi thực hiện lại."
        )
    return f"{base} Hãy chọn file dữ liệu phù hợp để tạo một cuộc trò chuyện mới rồi thực hiện lại."


def _has(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
