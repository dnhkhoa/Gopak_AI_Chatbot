from __future__ import annotations

import math
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from src.ingestion.normalizer import strip_accents
from src.rendering.formatters import format_duration, format_vn_number, humanize_column_name
from src.rendering.labels import display_label


class ColumnSemanticProfile(BaseModel):
    column_name: str
    display_name: str
    data_type: str
    semantic_role: str
    business_role: str | None = None
    is_identifier: bool
    is_row_index: bool
    is_technical_metadata: bool
    is_measure: bool
    is_dimension: bool
    is_datetime: bool
    is_duration: bool
    unique_ratio: float
    null_ratio: float
    constant_ratio: float
    unit: str | None = None
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class DatasetCapabilityProfile(BaseModel):
    domain_candidates: list[dict[str, Any]]
    selected_domain: str
    confidence: float
    dimensions: list[str]
    measures: list[str]
    datetime_columns: list[str]
    duration_columns: list[str]
    supported_analyses: list[str]
    unsupported_analyses: list[str]


class InsightCandidate(BaseModel):
    insight_id: str
    insight_type: str
    domain: str
    title: str
    business_question: str
    primary_entity: str | None
    primary_metric: str
    primary_value: float | int | str
    unit: str | None
    comparison_entities: list[str] = Field(default_factory=list)
    comparison_facts: list[dict[str, Any]] = Field(default_factory=list)
    evidence_rows: list[dict[str, Any]] = Field(default_factory=list)
    query_result_id: str
    relevance_score: float
    magnitude_score: float
    actionability_score: float
    evidence_score: float
    novelty_score: float
    redundancy_penalty: float = 0.0
    triviality_penalty: float = 0.0
    final_score: float
    allowed_claims: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    statement: str = ""
    facts: list[dict[str, Any]] = Field(default_factory=list)


class OverviewAnswerBrief(BaseModel):
    dataset_description: str
    record_count: int
    column_count: int
    date_range: dict[str, Any] | None = None
    business_dimensions: list[str]
    business_measures: list[str]
    selected_insights: list[InsightCandidate]
    comparison_facts: list[dict[str, Any]]
    recommended_chart: dict[str, Any] | None = None
    supporting_table: dict[str, Any] | None = None
    data_quality_notes: list[str]
    limitations: list[str]
    source_file_name: str
    filters: list[dict[str, Any]] = Field(default_factory=list)
    capability_profile: DatasetCapabilityProfile
    column_profiles: list[ColumnSemanticProfile]
    quality_warnings: list[str] = Field(default_factory=list)


TECHNICAL_NAME_PATTERNS = [
    r"^no$",
    r"^stt$",
    r"^so_thu_tu$",
    r"^index$",
    r"^row$",
    r"^row_id$",
    r"^unnamed",
    r"^uuid$",
    r"^guid$",
    r"internal_id",
    r"^hash$",
    r"source_row",
    r"sheet_row",
]
IDENTIFIER_HINTS = ["id", "uuid", "guid", "code", "ma_", "ma", "event_id", "transaction_id"]
GENERIC_FILLER = [
    "moi goc nhin do mot lat cat khac nhau",
    "du lieu cho thay nhieu thong tin huu ich",
    "ket qua co the ho tro ra quyet dinh",
    "can xem xet them de co ket luan chinh xac",
]


def build_domain_aware_overview(catalog: dict, source_file_name: str = "") -> OverviewAnswerBrief | None:
    table = (catalog.get("tables") or [None])[0]
    if not table:
        return None
    path = _resolve_parquet_path(table.get("parquet_path") or table.get("cache_path"))
    if path is None:
        return None
    df = pd.read_parquet(path)
    column_profiles = classify_columns(table, df)
    capability = build_capability_profile(column_profiles, table)
    candidates = generate_insight_candidates(table, df, column_profiles, capability)
    selected = select_diverse_insights(candidates, requested=3)
    date_range = _date_range(df, column_profiles)
    dimensions = [p.column_name for p in column_profiles if p.is_dimension and _is_business_column(p)]
    measures = [p.column_name for p in column_profiles if (p.is_measure or p.is_duration) and _is_business_column(p)]
    useful_columns = dimensions + measures + [p.column_name for p in column_profiles if p.is_datetime]
    warnings: list[str] = []
    if len(selected) < 2 and len(useful_columns) < 2:
        warnings.append("insufficient_business_columns")
    supporting_table = _supporting_table(selected)
    return OverviewAnswerBrief(
        dataset_description=_dataset_description(capability.selected_domain, len(df), len(df.columns), date_range),
        record_count=int(len(df)),
        column_count=int(len(df.columns)),
        date_range=date_range,
        business_dimensions=dimensions[:8],
        business_measures=measures[:8],
        selected_insights=selected,
        comparison_facts=_comparison_facts(selected),
        recommended_chart=_recommended_chart(capability, selected),
        supporting_table=supporting_table,
        data_quality_notes=_data_quality_notes(df, column_profiles),
        limitations=[
            "Kết quả mô tả dữ liệu đã import, không chứng minh quan hệ nhân quả hoặc nguyên nhân kỹ thuật bên ngoài file.",
            "Các phát hiện được tính từ các cột có sẵn và phụ thuộc chất lượng dữ liệu nguồn.",
        ],
        source_file_name=source_file_name or _source_file_name(table),
        filters=[],
        capability_profile=capability,
        column_profiles=column_profiles,
        quality_warnings=warnings,
    )


def classify_columns(table: dict, df: pd.DataFrame) -> list[ColumnSemanticProfile]:
    metadata = {col.get("normalized_name"): col for col in table.get("columns", [])}
    profiles: list[ColumnSemanticProfile] = []
    for column in df.columns:
        series = df[column]
        meta = metadata.get(column, {})
        display = str(meta.get("original_name") or column)
        normalized = _norm(f"{column} {display}")
        non_null = series.dropna()
        row_count = max(len(series), 1)
        unique_ratio = float(non_null.nunique(dropna=True) / max(len(non_null), 1)) if len(non_null) else 0.0
        null_ratio = float(series.isna().mean()) if len(series) else 1.0
        constant_ratio = float(non_null.value_counts(dropna=True, normalize=True).iloc[0]) if len(non_null) else 0.0
        existing_role = str(meta.get("semantic_role") or "")
        evidence: list[str] = []
        is_datetime = existing_role in {"start_time", "end_time"} or pd.api.types.is_datetime64_any_dtype(series) or _looks_datetime(column, display, series)
        is_duration = existing_role in {"duration", "duration_seconds"} or _has_any(normalized, ["duration", "downtime", "thoi_luong", "time_loss"])
        is_row_index = existing_role == "record_no" or _is_row_index_name(normalized) or _looks_like_row_sequence(series)
        is_technical = is_row_index or existing_role == "provenance" or _is_technical_name(normalized)
        is_identifier = (not is_row_index) and (not is_datetime) and (not is_duration) and _looks_like_identifier(column, display, series, unique_ratio)
        if is_row_index:
            role = "ROW_INDEX"
            evidence.append("row_index_pattern")
        elif is_identifier:
            role = "IDENTIFIER"
            evidence.append("identifier_pattern")
        elif is_technical:
            role = "TECHNICAL_METADATA"
            evidence.append("technical_name_or_role")
        elif is_datetime:
            role = "DATETIME"
            evidence.append("datetime_role_or_values")
        elif is_duration:
            role = "DURATION"
            evidence.append("duration_role_or_name")
        elif pd.api.types.is_bool_dtype(series):
            role = "BOOLEAN_FLAG"
        elif pd.api.types.is_numeric_dtype(series):
            role = "NUMERIC_MEASURE"
            evidence.append("numeric_dtype")
        elif unique_ratio > 0.85 and len(non_null) > 20:
            role = "TEXT_DESCRIPTION"
            evidence.append("high_cardinality_text")
        elif len(non_null):
            role = "CATEGORICAL_DIMENSION"
            evidence.append("categorical_values")
        else:
            role = "UNKNOWN"
        business_role = _business_role(column, display, existing_role, role)
        unit = "seconds" if role == "DURATION" and column.endswith("_seconds") else None
        profiles.append(
            ColumnSemanticProfile(
                column_name=str(column),
                display_name=display,
                data_type=str(series.dtype),
                semantic_role=role,
                business_role=business_role,
                is_identifier=is_identifier,
                is_row_index=is_row_index,
                is_technical_metadata=is_technical,
                is_measure=role == "NUMERIC_MEASURE",
                is_dimension=role in {"CATEGORICAL_DIMENSION", "TEXT_DESCRIPTION", "BOOLEAN_FLAG"},
                is_datetime=role == "DATETIME",
                is_duration=role == "DURATION",
                unique_ratio=round(unique_ratio, 4),
                null_ratio=round(null_ratio, 4),
                constant_ratio=round(constant_ratio, 4),
                unit=unit,
                confidence=0.95 if role in {"ROW_INDEX", "IDENTIFIER", "DURATION", "DATETIME"} else 0.82,
                evidence=evidence or ["fallback_rule"],
            )
        )
    return profiles


def build_capability_profile(profiles: list[ColumnSemanticProfile], table: dict | None = None) -> DatasetCapabilityProfile:
    roles = {p.business_role for p in profiles if p.business_role}
    source_text = _norm(" ".join(str((table or {}).get(key) or "") for key in ["table_name", "source", "source_file", "source_sheet"]))
    candidates: list[dict[str, Any]] = []
    source_has_loss = "loss" in source_text or "ton_that" in source_text
    source_has_entry = "entry" in source_text or "transaction" in source_text or "ra_vao" in source_text
    source_has_machine = "machine" in source_text or "downtime" in source_text
    machine_score = sum(role in roles for role in ["machine", "downtime_duration", "event_start", "event_end", "loss_reason", "loss_group"])
    loss_score = sum(role in roles for role in ["loss_group", "loss_reason"])
    entry_score = sum(role in roles for role in ["transaction_date", "gate", "vehicle", "quantity"])
    if "transaction_value" in roles and (source_has_entry or roles & {"transaction_date", "gate", "vehicle"}):
        entry_score += 1
    if source_has_loss:
        loss_score += 5
    if source_has_entry:
        entry_score += 2
    if source_has_machine:
        machine_score += 1
    candidates.extend(
        [
            {"domain": "machine_downtime", "score": machine_score / 6, "evidence": sorted(roles & {"machine", "downtime_duration", "event_start", "event_end", "loss_reason", "loss_group"})},
            {"domain": "loss_assignment", "score": loss_score / 4, "evidence": sorted(roles & {"loss_group", "loss_reason", "category", "status"})},
            {"domain": "entry_transaction", "score": entry_score / 6, "evidence": sorted(roles & {"transaction_value", "transaction_date", "quantity", "gate", "vehicle", "category"})},
        ]
    )
    best = max(candidates, key=lambda item: item["score"])
    selected = best["domain"] if best["score"] >= 0.25 else "generic_tabular"
    confidence = float(best["score"] if selected != "generic_tabular" else 0.45)
    dimensions = [p.column_name for p in profiles if p.is_dimension and _is_business_column(p)]
    measures = [p.column_name for p in profiles if p.is_measure and _is_business_column(p)]
    datetime_columns = [p.column_name for p in profiles if p.is_datetime and _is_business_column(p)]
    duration_columns = [p.column_name for p in profiles if p.is_duration and _is_business_column(p)]
    supported = ["record_count", "data_quality"]
    if dimensions and (measures or duration_columns):
        supported.append("ranked_contribution")
    if dimensions:
        supported.append("distribution")
    if datetime_columns and (measures or duration_columns):
        supported.append("trend")
    unsupported = []
    if not dimensions:
        unsupported.append("dimension_breakdown")
    if not measures and not duration_columns:
        unsupported.append("business_metric_summary")
    return DatasetCapabilityProfile(
        domain_candidates=sorted(candidates, key=lambda item: item["score"], reverse=True),
        selected_domain=selected,
        confidence=round(confidence, 3),
        dimensions=dimensions,
        measures=measures,
        datetime_columns=datetime_columns,
        duration_columns=duration_columns,
        supported_analyses=supported,
        unsupported_analyses=unsupported,
    )


def generate_insight_candidates(
    table: dict,
    df: pd.DataFrame,
    profiles: list[ColumnSemanticProfile],
    capability: DatasetCapabilityProfile,
) -> list[InsightCandidate]:
    domain = capability.selected_domain
    if domain == "machine_downtime":
        candidates = _machine_downtime_candidates(table, df, profiles)
    elif domain == "loss_assignment":
        candidates = _loss_assignment_candidates(table, df, profiles)
    elif domain == "entry_transaction":
        candidates = _entry_transaction_candidates(table, df, profiles)
    else:
        candidates = _generic_candidates(table, df, profiles)
    candidates.extend(_significant_quality_candidates(df, profiles, domain))
    filtered = [item for item in candidates if not TrivialInsightFilter.is_trivial(item, profiles)]
    return sorted(filtered, key=lambda item: item.final_score, reverse=True)


class TrivialInsightFilter:
    @staticmethod
    def is_trivial(candidate: InsightCandidate, profiles: list[ColumnSemanticProfile]) -> bool:
        profile_map = {p.column_name: p for p in profiles}
        evidence_cols = {str(row.get("column") or row.get("dimension") or "") for row in candidate.evidence_rows}
        technical = [profile_map[col] for col in evidence_cols if col in profile_map and not _is_business_column(profile_map[col])]
        if technical:
            return True
        text = _norm(f"{candidate.title} {candidate.statement} {candidate.primary_metric} {candidate.business_question}")
        if any(term in text for term in ["day du 100", "co du lieu day du", "xuat hien 1 lan", "100% gia tri khac nhau"]):
            return True
        if candidate.triviality_penalty >= 0.8:
            return True
        return False


def select_diverse_insights(candidates: list[InsightCandidate], requested: int = 3) -> list[InsightCandidate]:
    selected: list[InsightCandidate] = []
    type_counts: dict[str, int] = {}
    metrics: set[str] = set()
    entities: set[str] = set()
    for candidate in candidates:
        if type_counts.get(candidate.insight_type, 0) >= 2:
            continue
        if len(selected) >= 2 and candidate.primary_metric in metrics and candidate.primary_entity in entities:
            continue
        selected.append(candidate)
        type_counts[candidate.insight_type] = type_counts.get(candidate.insight_type, 0) + 1
        metrics.add(candidate.primary_metric)
        if candidate.primary_entity:
            entities.add(candidate.primary_entity)
        if len(selected) >= requested:
            break
    if len(selected) < min(requested, len(candidates)):
        for candidate in candidates:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= requested:
                break
    return selected[:requested]


def validate_overview_brief(brief: OverviewAnswerBrief) -> dict[str, Any]:
    errors: list[str] = []
    for insight in brief.selected_insights:
        if not insight.facts:
            errors.append(f"{insight.insight_id}:missing_facts")
        if insight.triviality_penalty >= 0.8:
            errors.append(f"{insight.insight_id}:trivial")
        for row in insight.evidence_rows:
            column = str(row.get("column") or row.get("dimension") or "")
            profile = next((p for p in brief.column_profiles if p.column_name == column), None)
            if profile and not _is_business_column(profile):
                errors.append(f"{insight.insight_id}:technical_column:{column}")
    diversity = len({item.insight_type for item in brief.selected_insights}) >= min(2, len(brief.selected_insights))
    if not diversity and len(brief.selected_insights) > 1:
        errors.append("low_diversity")
    business_terms = _norm(" ".join(item.statement for item in brief.selected_insights))
    generic_schema_ok = bool(brief.business_dimensions) and bool(brief.business_measures) and len(brief.selected_insights) >= 2
    if not any(term in business_terms for term in ["machine", "may", "downtime", "loss", "ton that", "transaction", "giao dich", "gia tri", "cong", "nhom", "nguyen nhan"]) and not generic_schema_ok:
        errors.append("missing_business_concepts")
    return {"passed": not errors, "errors": errors}


def _machine_downtime_candidates(table: dict, df: pd.DataFrame, profiles: list[ColumnSemanticProfile]) -> list[InsightCandidate]:
    duration = _business_col(profiles, "downtime_duration") or _first(profiles, lambda p: p.is_duration)
    machine = _business_col(profiles, "machine")
    start = _business_col(profiles, "event_start") or _first(profiles, lambda p: p.is_datetime)
    cause = _business_col(profiles, "loss_reason") or _business_col(profiles, "loss_group")
    if not duration:
        return _generic_candidates(table, df, profiles)
    work = df.copy()
    work["_metric"] = pd.to_numeric(work[duration], errors="coerce").fillna(0)
    candidates = [
        _total_metric_candidate("total_downtime", "machine_downtime", "Tổng downtime", "Tổng thời gian dừng máy trong file", work["_metric"].sum(), "seconds", len(work), "Tổng downtime trong file là {value} trên {count} bản ghi.", "downtime_duration"),
    ]
    if machine and machine in work.columns:
        by_total = _group_duration(work, machine, "_metric")
        candidates.append(_ranked_duration_candidate(by_total, machine, "top_machine_downtime", "Máy đứng đầu về tổng downtime", "Máy nào tạo tổng downtime lớn nhất?", "machine_downtime", "{entity} có tổng downtime cao nhất: {duration}, gồm {count} lần dừng và trung bình {avg} mỗi lần.", metric_name="machine_total_downtime"))
        by_count = _group_count(work, machine, "_metric")
        candidates.append(_ranked_count_candidate(by_count, machine, "top_machine_events", "Máy đứng đầu về số lần dừng", "Máy nào dừng nhiều lần nhất?", "machine_downtime", "{entity} có số lần dừng cao nhất: {count} lần; tổng downtime của nhóm này là {duration}."))
    if cause and cause in work.columns:
        by_cause = _group_duration(work, cause, "_metric")
        candidates.append(_ranked_duration_candidate(by_cause, cause, "top_cause_downtime", "Nguyên nhân/nhóm tổn thất nổi bật", "Nguyên nhân hoặc nhóm nào đóng góp downtime nhiều nhất?", "machine_downtime", "{entity} là nhóm/nguyên nhân có tổng downtime cao nhất: {duration}, với {count} lần dừng.", metric_name="cause_total_downtime"))
    if start and start in work.columns:
        trend = _time_trend(work, start, "_metric")
        if not trend.empty:
            top = trend.iloc[0]
            value = _fmt_duration(float(top["total"]))
            count = _fmt_int(int(top["count"]))
            candidates.append(
                _candidate(
                    insight_type="trend",
                    domain="machine_downtime",
                    title="Ngày có downtime cao nhất",
                    business_question="Downtime đạt đỉnh vào thời điểm nào?",
                    primary_entity=str(top["period"]),
                    primary_metric="daily_total_downtime",
                    primary_value=float(top["total"]),
                    unit="seconds",
                    statement=f"Downtime đạt đỉnh vào {top['period']} với {value} từ {count} lần dừng.",
                    facts=[("peak_duration", float(top["total"]) / 3600, value), ("peak_count", float(top["count"]), count)],
                    evidence_rows=[{"dimension": start, "entity": str(top["period"]), "metric": "total_downtime", "value": float(top["total"])}],
                    relevance=0.95,
                    magnitude=0.78,
                    actionability=0.82,
                )
            )
    return [item for item in candidates if item is not None]


def _loss_assignment_candidates(table: dict, df: pd.DataFrame, profiles: list[ColumnSemanticProfile]) -> list[InsightCandidate]:
    group = _business_col(profiles, "loss_group") or _business_col(profiles, "category")
    reason = _business_col(profiles, "loss_reason") or group
    duration = _business_col(profiles, "downtime_duration") or _first(profiles, lambda p: p.is_duration)
    candidates: list[InsightCandidate] = []
    dim = group or reason
    if dim and dim in df.columns:
        grouped = df.groupby(dim, dropna=False).size().sort_values(ascending=False).reset_index(name="count")
        if not grouped.empty:
            top = grouped.iloc[0]
            count = int(top["count"])
            pct = _safe_pct(count, len(df))
            candidates.append(
                _candidate(
                    insight_type="distribution",
                    domain="loss_assignment",
                    title="Nhóm tổn thất xuất hiện nhiều nhất",
                    business_question="Nhóm/loại tổn thất nào chiếm tỷ trọng lớn nhất?",
                    primary_entity=str(top[dim]),
                    primary_metric="row_count",
                    primary_value=count,
                    unit="records",
                    statement=f"{top[dim]} xuất hiện nhiều nhất với {_fmt_int(count)} bản ghi, chiếm {_fmt_pct(pct)} tổng số bản ghi.",
                    facts=[("top_count", float(count), _fmt_int(count)), ("top_pct", pct, _fmt_pct(pct))],
                    evidence_rows=[{"dimension": dim, "entity": str(top[dim]), "metric": "row_count", "value": count}],
                    relevance=0.92,
                    magnitude=0.72,
                    actionability=0.76,
                )
            )
            top3 = int(grouped["count"].head(3).sum())
            top3_pct = _safe_pct(top3, len(df))
            candidates.append(
                _candidate(
                    insight_type="concentration",
                    domain="loss_assignment",
                    title="Mức tập trung của các nhóm đầu",
                    business_question="Tổn thất có tập trung vào ít nhóm không?",
                    primary_entity="top_3",
                    primary_metric="row_count_share",
                    primary_value=top3_pct,
                    unit="percent",
                    statement=f"Ba nhóm/loại đứng đầu chiếm {_fmt_pct(top3_pct)} với {_fmt_int(top3)} bản ghi, cho thấy mức tập trung của phân loại tổn thất.",
                    facts=[("top3_count", float(top3), _fmt_int(top3)), ("top3_pct", top3_pct, _fmt_pct(top3_pct))],
                    evidence_rows=[{"dimension": dim, "entity": "top_3", "metric": "row_count_share", "value": top3_pct}],
                    relevance=0.85,
                    magnitude=0.70,
                    actionability=0.72,
                )
            )
    if duration and dim and duration in df.columns:
        work = df.copy()
        work["_metric"] = pd.to_numeric(work[duration], errors="coerce").fillna(0)
        candidates.append(_ranked_duration_candidate(_group_duration(work, dim, "_metric"), dim, "loss_duration", "Nhóm tổn thất đóng góp thời lượng lớn nhất", "Nhóm nào đóng góp tổng thời lượng lớn nhất?", "loss_assignment", "{entity} có tổng thời lượng cao nhất: {duration}, gồm {count} bản ghi."))
    return [item for item in candidates if item is not None]


def _entry_transaction_candidates(table: dict, df: pd.DataFrame, profiles: list[ColumnSemanticProfile]) -> list[InsightCandidate]:
    value = _business_col(profiles, "transaction_value") or _first(profiles, lambda p: p.is_measure)
    date = _business_col(profiles, "transaction_date") or _first(profiles, lambda p: p.is_datetime)
    category = _business_col(profiles, "gate") or _business_col(profiles, "vehicle") or _business_col(profiles, "category") or _first(profiles, lambda p: p.is_dimension)
    candidates: list[InsightCandidate] = []
    if value and value in df.columns:
        numeric = pd.to_numeric(df[value], errors="coerce").fillna(0)
        total = float(numeric.sum())
        avg = float(numeric.mean()) if len(numeric) else 0.0
        candidates.append(
            _candidate(
                insight_type="metric_summary",
                domain="entry_transaction",
                title="Tổng giá trị giao dịch",
                business_question="Tổng giá trị giao dịch trong file là bao nhiêu?",
                primary_entity=None,
                primary_metric=value,
                primary_value=total,
                unit=None,
                statement=f"Tổng giá trị giao dịch đạt {_fmt_number(total)} trên {_fmt_int(len(df))} bản ghi; giá trị trung bình là {_fmt_number(avg)}.",
                facts=[("total_value", total, _fmt_number(total)), ("avg_value", avg, _fmt_number(avg)), ("row_count", float(len(df)), _fmt_int(len(df)))],
                evidence_rows=[{"column": value, "metric": "sum", "value": total}],
                relevance=0.92,
                magnitude=0.75,
                actionability=0.78,
            )
        )
    if category and category in df.columns:
        grouped = df.groupby(category, dropna=False).size().sort_values(ascending=False).reset_index(name="count")
        if not grouped.empty:
            top = grouped.iloc[0]
            count = int(top["count"])
            pct = _safe_pct(count, len(df))
            candidates.append(
                _candidate(
                    insight_type="distribution",
                    domain="entry_transaction",
                    title="Nhóm/cửa cổng giao dịch nổi bật",
                    business_question="Đối tượng hoặc nhóm nào xuất hiện nhiều nhất?",
                    primary_entity=str(top[category]),
                    primary_metric="transaction_count",
                    primary_value=count,
                    unit="records",
                    statement=f"{top[category]} có số giao dịch/ghi nhận cao nhất với {_fmt_int(count)} bản ghi, chiếm {_fmt_pct(pct)}.",
                    facts=[("top_count", float(count), _fmt_int(count)), ("top_pct", pct, _fmt_pct(pct))],
                    evidence_rows=[{"dimension": category, "entity": str(top[category]), "metric": "transaction_count", "value": count}],
                    relevance=0.86,
                    magnitude=0.68,
                    actionability=0.70,
                )
            )
    if date and date in df.columns:
        trend = _time_trend(df.assign(_metric=1), date, "_metric")
        if not trend.empty:
            top = trend.iloc[0]
            count = int(top["count"])
            candidates.append(
                _candidate(
                    insight_type="trend",
                    domain="entry_transaction",
                    title="Ngày có giao dịch cao nhất",
                    business_question="Thời điểm nào có lượng giao dịch cao nhất?",
                    primary_entity=str(top["period"]),
                    primary_metric="transaction_count",
                    primary_value=count,
                    unit="records",
                    statement=f"Lượng giao dịch/ghi nhận đạt đỉnh vào {top['period']} với {_fmt_int(count)} bản ghi.",
                    facts=[("peak_count", float(count), _fmt_int(count))],
                    evidence_rows=[{"dimension": date, "entity": str(top["period"]), "metric": "transaction_count", "value": count}],
                    relevance=0.95,
                    magnitude=0.85,
                    actionability=0.85,
                )
            )
    return candidates


def _generic_candidates(table: dict, df: pd.DataFrame, profiles: list[ColumnSemanticProfile]) -> list[InsightCandidate]:
    candidates: list[InsightCandidate] = []
    dim = _first(profiles, lambda p: p.is_dimension)
    measure = _first(profiles, lambda p: p.is_measure)
    date = _first(profiles, lambda p: p.is_datetime)
    if dim and dim in df.columns:
        grouped = df.groupby(dim, dropna=False).size().sort_values(ascending=False).reset_index(name="count")
        if not grouped.empty:
            top = grouped.iloc[0]
            count = int(top["count"])
            pct = _safe_pct(count, len(df))
            candidates.append(
                _candidate(
                    insight_type="distribution",
                    domain="generic_tabular",
                    title="Phân bố theo cột nghiệp vụ",
                    business_question="Giá trị nào xuất hiện nhiều nhất trong cột phân loại?",
                    primary_entity=str(top[dim]),
                    primary_metric="row_count",
                    primary_value=count,
                    unit="records",
                    statement=f"{humanize_column_name(dim, {'tables':[table]})}: {top[dim]} xuất hiện nhiều nhất với {_fmt_int(count)} bản ghi, chiếm {_fmt_pct(pct)}.",
                    facts=[("top_count", float(count), _fmt_int(count)), ("top_pct", pct, _fmt_pct(pct))],
                    evidence_rows=[{"dimension": dim, "entity": str(top[dim]), "metric": "row_count", "value": count}],
                    relevance=0.70,
                    magnitude=0.60,
                    actionability=0.55,
                )
            )
    if measure and measure in df.columns:
        numeric = pd.to_numeric(df[measure], errors="coerce")
        total = float(numeric.sum(skipna=True))
        avg = float(numeric.mean(skipna=True)) if numeric.notna().any() else 0.0
        candidates.append(
            _candidate(
                insight_type="metric_summary",
                domain="generic_tabular",
                title="Tổng hợp chỉ số số",
                business_question="Cột số nào có thể dùng làm metric tổng quan?",
                primary_entity=None,
                primary_metric=measure,
                primary_value=total,
                unit=None,
                statement=f"{humanize_column_name(measure, {'tables':[table]})} có tổng {_fmt_number(total)} và trung bình {_fmt_number(avg)}.",
                facts=[("measure_total", total, _fmt_number(total)), ("measure_avg", avg, _fmt_number(avg))],
                evidence_rows=[{"column": measure, "metric": "sum", "value": total}],
                relevance=0.66,
                magnitude=0.56,
                actionability=0.50,
            )
        )
    if date and date in df.columns:
        dr = _date_range(df, profiles)
        if dr:
            candidates.append(
                _candidate(
                    insight_type="coverage",
                    domain="generic_tabular",
                    title="Phạm vi thời gian",
                    business_question="Dữ liệu bao phủ khoảng thời gian nào?",
                    primary_entity=None,
                    primary_metric="date_range",
                    primary_value=str(dr),
                    unit=None,
                    statement=f"Dữ liệu có phạm vi thời gian từ {dr['start']} đến {dr['end']}.",
                    facts=[],
                    evidence_rows=[{"dimension": date, "metric": "date_range", "value": str(dr)}],
                    relevance=0.62,
                    magnitude=0.50,
                    actionability=0.45,
                )
            )
    return candidates


def _significant_quality_candidates(df: pd.DataFrame, profiles: list[ColumnSemanticProfile], domain: str) -> list[InsightCandidate]:
    candidates: list[InsightCandidate] = []
    business = [p for p in profiles if _is_business_column(p)]
    missing = [p for p in business if p.null_ratio >= 0.10]
    if missing:
        top = max(missing, key=lambda p: p.null_ratio)
        pct = top.null_ratio * 100
        candidates.append(
            _candidate(
                insight_type="data_quality",
                domain=domain,
                title="Thiếu dữ liệu đáng chú ý",
                business_question="Cột nghiệp vụ nào bị thiếu dữ liệu đáng kể?",
                primary_entity=top.display_name,
                primary_metric="missing_rate",
                primary_value=pct,
                unit="percent",
                statement=f"Cột {top.display_name} bị thiếu {_fmt_pct(pct)} giá trị, có thể ảnh hưởng các phân tích liên quan đến cột này.",
                facts=[("missing_pct", pct, _fmt_pct(pct))],
                evidence_rows=[{"column": top.column_name, "metric": "missing_rate", "value": pct}],
                relevance=0.62,
                magnitude=min(0.75, pct / 80),
                actionability=0.60,
            )
        )
    return candidates


def _candidate(
    *,
    insight_type: str,
    domain: str,
    title: str,
    business_question: str,
    primary_entity: str | None,
    primary_metric: str,
    primary_value: float | int | str,
    unit: str | None,
    statement: str,
    facts: list[tuple[str, float, str]],
    evidence_rows: list[dict[str, Any]],
    relevance: float,
    magnitude: float,
    actionability: float,
    evidence: float = 1.0,
    novelty: float = 0.75,
    triviality: float = 0.0,
) -> InsightCandidate:
    final = 0.25 * relevance + 0.20 * magnitude + 0.20 * actionability + 0.15 * evidence + 0.10 * novelty + 0.10 * relevance - triviality
    return InsightCandidate(
        insight_id=str(uuid.uuid4()),
        insight_type=insight_type,
        domain=domain,
        title=title,
        business_question=business_question,
        primary_entity=primary_entity,
        primary_metric=primary_metric,
        primary_value=primary_value,
        unit=unit,
        comparison_entities=[],
        comparison_facts=[],
        evidence_rows=evidence_rows,
        query_result_id=str(uuid.uuid4()),
        relevance_score=round(relevance, 3),
        magnitude_score=round(magnitude, 3),
        actionability_score=round(actionability, 3),
        evidence_score=round(evidence, 3),
        novelty_score=round(novelty, 3),
        redundancy_penalty=0.0,
        triviality_penalty=round(triviality, 3),
        final_score=round(final, 4),
        allowed_claims=[statement],
        limitations=[],
        statement=statement,
        facts=[{"key": key, "value": value, "display": display} for key, value, display in facts],
    )


def _total_metric_candidate(insight_type: str, domain: str, title: str, question: str, total_seconds: float, unit: str, row_count: int, template: str, metric: str) -> InsightCandidate:
    value_display = _fmt_duration(total_seconds)
    count_display = _fmt_int(row_count)
    return _candidate(
        insight_type=insight_type,
        domain=domain,
        title=title,
        business_question=question,
        primary_entity=None,
        primary_metric=metric,
        primary_value=float(total_seconds),
        unit=unit,
        statement=template.format(value=value_display, count=count_display),
        facts=[("total_duration", float(total_seconds) / 3600, value_display), ("row_count", float(row_count), count_display)],
        evidence_rows=[{"metric": metric, "value": float(total_seconds)}],
        relevance=0.90,
        magnitude=0.75,
        actionability=0.72,
    )


def _ranked_duration_candidate(
    grouped: pd.DataFrame,
    dimension: str,
    insight_type: str,
    title: str,
    question: str,
    domain: str,
    template: str,
    metric_name: str = "total_downtime",
) -> InsightCandidate | None:
    if grouped.empty:
        return None
    top = grouped.iloc[0]
    duration = float(top["total_duration_seconds"])
    count = int(top["row_count"])
    avg = float(top["avg_duration_seconds"])
    entity = str(top[dimension])
    duration_display = _fmt_duration(duration)
    count_display = _fmt_int(count)
    avg_display = _fmt_duration(avg)
    return _candidate(
        insight_type=insight_type,
        domain=domain,
        title=title,
        business_question=question,
        primary_entity=entity,
        primary_metric=metric_name,
        primary_value=duration,
        unit="seconds",
        statement=template.format(entity=entity, duration=duration_display, count=count_display, avg=avg_display),
        facts=[("duration", duration / 3600, duration_display), ("count", float(count), count_display), ("avg", avg / 3600, avg_display)],
        evidence_rows=[{"dimension": dimension, "entity": entity, "metric": "total_downtime", "value": duration}],
        relevance=0.96,
        magnitude=0.80,
        actionability=0.85,
    )


def _ranked_count_candidate(grouped: pd.DataFrame, dimension: str, insight_type: str, title: str, question: str, domain: str, template: str) -> InsightCandidate | None:
    if grouped.empty:
        return None
    top = grouped.iloc[0]
    count = int(top["row_count"])
    duration = float(top.get("total_duration_seconds", 0.0))
    entity = str(top[dimension])
    duration_display = _fmt_duration(duration)
    count_display = _fmt_int(count)
    return _candidate(
        insight_type=insight_type,
        domain=domain,
        title=title,
        business_question=question,
        primary_entity=entity,
        primary_metric="event_count",
        primary_value=count,
        unit="records",
        statement=template.format(entity=entity, count=count_display, duration=duration_display),
        facts=[("count", float(count), count_display), ("duration", duration / 3600, duration_display)],
        evidence_rows=[{"dimension": dimension, "entity": entity, "metric": "event_count", "value": count}],
        relevance=0.86,
        magnitude=0.68,
        actionability=0.74,
    )


def _group_duration(df: pd.DataFrame, column: str, metric: str) -> pd.DataFrame:
    return (
        df.groupby(column, dropna=False)
        .agg(total_duration_seconds=(metric, "sum"), row_count=(metric, "size"), avg_duration_seconds=(metric, "mean"))
        .sort_values("total_duration_seconds", ascending=False)
        .reset_index()
    )


def _group_count(df: pd.DataFrame, column: str, metric: str) -> pd.DataFrame:
    return (
        df.groupby(column, dropna=False)
        .agg(row_count=(metric, "size"), total_duration_seconds=(metric, "sum"))
        .sort_values("row_count", ascending=False)
        .reset_index()
    )


def _time_trend(df: pd.DataFrame, column: str, metric: str) -> pd.DataFrame:
    dates = pd.to_datetime(df[column], errors="coerce")
    valid = df.assign(_period=dates.dt.date).dropna(subset=["_period"])
    if valid.empty:
        return pd.DataFrame()
    return (
        valid.groupby("_period", dropna=False)
        .agg(total=(metric, "sum"), count=(metric, "size"))
        .sort_values("total", ascending=False)
        .reset_index()
        .rename(columns={"_period": "period"})
    )


def _date_range(df: pd.DataFrame, profiles: list[ColumnSemanticProfile]) -> dict[str, Any] | None:
    for profile in profiles:
        if not profile.is_datetime or profile.column_name not in df.columns:
            continue
        dates = pd.to_datetime(df[profile.column_name], errors="coerce").dropna()
        if dates.empty:
            continue
        return {"column": profile.column_name, "start": str(dates.min().date()), "end": str(dates.max().date())}
    return None


def _data_quality_notes(df: pd.DataFrame, profiles: list[ColumnSemanticProfile]) -> list[str]:
    notes = []
    business = [p for p in profiles if _is_business_column(p)]
    missing = [p for p in business if p.null_ratio >= 0.10]
    if missing:
        top = max(missing, key=lambda p: p.null_ratio)
        notes.append(f"Cột {top.display_name} thiếu {_fmt_pct(top.null_ratio * 100)} giá trị.")
    duplicate_count = int(df.duplicated().sum()) if len(df) else 0
    if duplicate_count:
        notes.append(f"Có {_fmt_int(duplicate_count)} dòng trùng lặp hoàn toàn.")
    if not notes:
        notes.append("Không phát hiện tỷ lệ thiếu dữ liệu vượt 10% trên các cột nghiệp vụ chính.")
    return notes


def _dataset_description(domain: str, rows: int, cols: int, date_range: dict[str, Any] | None) -> str:
    label = {
        "machine_downtime": "dữ liệu dừng máy/downtime",
        "loss_assignment": "dữ liệu phân loại tổn thất",
        "entry_transaction": "dữ liệu giao dịch/ra vào",
        "generic_tabular": "dữ liệu bảng tổng hợp",
    }.get(domain, "dữ liệu bảng")
    period = f" từ {date_range['start']} đến {date_range['end']}" if date_range else ""
    return f"File chứa {label}{period}, gồm {_fmt_int(rows)} bản ghi và {_fmt_int(cols)} cột."


def _supporting_table(insights: list[InsightCandidate]) -> dict[str, Any] | None:
    columns = ["Phát hiện", "Đối tượng", "Chỉ số", "Giá trị"]
    rows = []
    for item in insights:
        rows.append(
            {
                "Phát hiện": item.title,
                "Đối tượng": item.primary_entity or "Toàn bộ file",
                "Chỉ số": display_label(item.primary_metric),
                "Giá trị": item.facts[0]["display"] if item.facts else str(item.primary_value),
            }
        )
    return {"columns": columns, "rows": rows} if rows else None


def _comparison_facts(insights: list[InsightCandidate]) -> list[dict[str, Any]]:
    if len(insights) < 2:
        return []
    return [
        {
            "type": "metric_contrast",
            "fact": f"{insights[0].title} và {insights[1].title} dùng hai góc nhìn khác nhau: {display_label(insights[0].primary_metric)} so với {display_label(insights[1].primary_metric)}.",
        }
    ]


def _recommended_chart(capability: DatasetCapabilityProfile, insights: list[InsightCandidate]) -> dict[str, Any] | None:
    if not insights:
        return None
    first = insights[0]
    if first.primary_entity:
        return {"type": "bar", "dimension": "primary_entity", "metric": first.primary_metric, "reason": first.title}
    if "trend" in capability.supported_analyses:
        return {"type": "line", "metric": first.primary_metric, "reason": "trend_supported"}
    return None


def human_usefulness_score(brief: OverviewAnswerBrief) -> dict[str, Any]:
    text = _norm(" ".join(item.statement for item in brief.selected_insights))
    technical = any(not _is_business_column(p) and p.column_name in text for p in brief.column_profiles)
    criteria = {
        "Domain relevance": 2 if brief.capability_profile.selected_domain != "generic_tabular" or brief.business_dimensions or brief.business_measures else 1,
        "Business usefulness": 2 if len(brief.selected_insights) >= 2 and not technical else 0,
        "Evidence specificity": 2 if all(item.facts for item in brief.selected_insights) else 0,
        "Non-triviality": 2 if all(item.triviality_penalty < 0.8 for item in brief.selected_insights) else 0,
        "Diversity": 2 if len({item.insight_type for item in brief.selected_insights}) >= min(2, len(brief.selected_insights)) else 1,
        "Clarity": 2 if brief.dataset_description and brief.limitations else 1,
        "Actionability": 2 if any(item.actionability_score >= 0.7 for item in brief.selected_insights) else 1,
        "Limitation quality": 2 if brief.limitations else 0,
    }
    total = sum(criteria.values())
    return {"criteria": criteria, "total": total, "max": 16}


def response_quality_errors(text: str) -> list[str]:
    normalized = _norm(text)
    return [f"generic_filler:{phrase}" for phrase in GENERIC_FILLER if phrase in normalized]


def _business_role(column: str, display: str, existing_role: str, semantic_role: str) -> str | None:
    text = _norm(f"{column} {display} {existing_role}")
    if existing_role == "machine" or _has_any(text, ["machine", " may", "ten_may"]):
        return "machine"
    if existing_role in {"duration", "duration_seconds"} or _has_any(text, ["downtime", "duration", "thoi_luong", "time_loss"]):
        return "downtime_duration"
    if existing_role == "start_time" or _has_any(text, ["start", "bat_dau", "ngay", "date", "time"]):
        return "event_start" if "end" not in text and "ket_thuc" not in text else "event_end"
    if existing_role == "end_time" or _has_any(text, ["end", "ket_thuc"]):
        return "event_end"
    if existing_role == "loss_group" or _has_any(text, ["nhom_ton_that", "loss_group", "loss_category", "ton_that_group", "bo_phan_ton_that"]):
        return "loss_group"
    if _has_any(text, ["loss", "ton_that"]) and _has_any(text, ["group", "category", "nhom", "loai"]):
        return "loss_group"
    if existing_role in {"loss_name", "loss_type"} or _has_any(text, ["nguyen_nhan", "reason", "loss", "ten_ton_that", "loai_ton_that"]):
        return "loss_reason"
    if _has_any(text, ["gia_tri_can", "value", "amount", "price", "total", "weight"]):
        return "transaction_value"
    if _has_any(text, ["cong", "gate"]):
        return "gate"
    if _has_any(text, ["bien_so", "vehicle", "xe"]):
        return "vehicle"
    if semantic_role == "DATETIME":
        return "transaction_date"
    if semantic_role == "NUMERIC_MEASURE":
        return "quantity"
    if semantic_role == "CATEGORICAL_DIMENSION":
        return "category"
    return None


def _is_business_column(profile: ColumnSemanticProfile) -> bool:
    return (
        not (profile.is_row_index or profile.is_identifier or profile.is_technical_metadata)
        and profile.semantic_role not in {"UNKNOWN"}
        and profile.constant_ratio < 0.98
    )


def _business_col(profiles: list[ColumnSemanticProfile], role: str) -> str | None:
    if role == "downtime_duration":
        preferred = next(
            (
                p
                for p in profiles
                if p.business_role == role
                and _is_business_column(p)
                and (p.column_name == "duration_seconds" or p.column_name.endswith("_seconds"))
                and "reported" not in p.column_name
                and "calculated" not in p.column_name
                and "difference" not in p.column_name
            ),
            None,
        )
        if preferred:
            return preferred.column_name
    profile = next((p for p in profiles if p.business_role == role and _is_business_column(p)), None)
    return profile.column_name if profile else None


def _first(profiles: list[ColumnSemanticProfile], predicate) -> str | None:
    if any(predicate(p) and p.column_name == "duration_seconds" and _is_business_column(p) for p in profiles):
        return "duration_seconds"
    profile = next((p for p in profiles if predicate(p) and _is_business_column(p)), None)
    return profile.column_name if profile else None


def _is_row_index_name(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in TECHNICAL_NAME_PATTERNS)


def _is_technical_name(text: str) -> bool:
    return text.startswith("_") or any(re.search(pattern, text) for pattern in TECHNICAL_NAME_PATTERNS) or _has_any(text, ["created_at", "updated_at", "internal", "provenance", "duplicate_group"])


def _looks_like_row_sequence(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if len(numeric) < 10:
        return False
    values = numeric.astype(float).to_numpy()
    if len(set(values[: min(len(values), 100)])) != min(len(values), 100):
        return False
    diffs = pd.Series(values).diff().dropna()
    if diffs.empty:
        return False
    sequential_ratio = float((diffs == 1).mean())
    starts_near_one = abs(values[0] - 1) <= 1
    return sequential_ratio >= 0.98 and starts_near_one


def _looks_like_identifier(column: str, display: str, series: pd.Series, unique_ratio: float) -> bool:
    text = _norm(f"{column} {display}")
    if _has_any(text, IDENTIFIER_HINTS) and unique_ratio >= 0.80:
        return True
    if unique_ratio >= 0.98 and not pd.api.types.is_numeric_dtype(series) and len(series.dropna()) > 20:
        return True
    sample = " ".join(str(item) for item in series.dropna().astype(str).head(20).tolist())
    if re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", sample.lower()):
        return True
    return False


def _looks_datetime(column: str, display: str, series: pd.Series) -> bool:
    text = _norm(f"{column} {display}")
    if not _has_any(text, ["date", "time", "ngay", "thang", "bat_dau", "ket_thuc"]):
        return False
    parsed = pd.to_datetime(series, errors="coerce")
    return bool(parsed.notna().mean() >= 0.60)


def _has_any(text: str, terms: list[str] | set[str]) -> bool:
    return any(term in text for term in terms)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", strip_accents(str(value)).lower().replace("đ", "d")).strip()


def _safe_pct(part: float, total: float) -> float:
    return float(part / total * 100) if total else 0.0


def _fmt_pct(value: float) -> str:
    return f"{format_vn_number(value, 1)}%"


def _fmt_int(value: int | float) -> str:
    return format_vn_number(float(value), 0)


def _fmt_number(value: float) -> str:
    return format_vn_number(float(value), 2)


def _fmt_duration(seconds: float) -> str:
    return format_duration(float(seconds))["primary"]


def _resolve_parquet_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.exists():
        return path
    candidate = Path.cwd() / str(value)
    return candidate if candidate.exists() else None


def _source_file_name(table: dict) -> str:
    source = str(table.get("source") or table.get("source_file") or "")
    return Path(source.split(" / ", 1)[0]).name
