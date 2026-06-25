from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.query.schemas import QueryPlan
from src.query_understanding.text import normalize_text


class RequestContract(BaseModel):
    relation_to_previous_turn: str
    intent: str
    source_file_id: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    aggregations: list[str] = Field(default_factory=list)
    filters: list[dict] = Field(default_factory=list)
    time_range: dict | None = None
    time_grain: str | None = None
    ranking: str | None = None
    limit: int | None = None
    derived_metrics: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(default_factory=list)
    requested_chart_type: str | None = None
    requested_insight_count: int | None = None
    report_type: str | None = None
    report_detail_level: str | None = None
    report_sections: list[str] = Field(default_factory=list)
    commentary_requirements: list[str] = Field(default_factory=list)
    inherited_fields: list[str] = Field(default_factory=list)
    explicitly_reset_fields: list[str] = Field(default_factory=list)


class ChartContract(BaseModel):
    chart_type: str
    dimension: str
    metric: str
    aggregation: str
    x_axis_unit: str | None = None
    y_axis_unit: str | None = None
    tooltip_unit: str | None = None
    source_result_id: str
    source_turn_id: str
    expected_category_count: int | None = None
    time_grain: str | None = None


@dataclass
class CoverageResult:
    requested: list[str] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "planned": self.planned,
            "missing": self.missing,
            "unexpected": self.unexpected,
        }


def new_lineage(conversation_id: str, source_file_id: str | None) -> dict[str, str | None]:
    turn_id = str(uuid4())
    return {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "source_file_id": source_file_id,
        "request_contract_id": str(uuid4()),
        "query_plan_id": str(uuid4()),
        "query_result_id": str(uuid4()),
        "answer_brief_id": str(uuid4()),
        "chart_spec_id": str(uuid4()),
        "report_artifact_id": str(uuid4()),
    }


def build_request_contract(question: str, source_file_id: str | None, has_previous_result: bool) -> RequestContract:
    q = normalize_text(question)
    outputs: list[str] = []
    report_sections: list[str] = []
    chart_type: str | None = None
    intent = "query"
    if _is_report(q):
        intent = "report"
        outputs.append("report")
        report_sections = _report_sections(q)
    elif _is_chart(q):
        intent = "chart"
        outputs.append("chart")
        chart_type = _requested_chart_type(q)
    elif _requests_commentary(q):
        intent = "commentary"
    dimensions = _dimensions(q)
    metrics = _metrics(q)
    aggregations = _aggregations(q)
    derived = []
    if any(term in q for term in ["ty le", "phan tram", "ty trong"]):
        derived.append("percentage")
    time_grain = _time_grain(q)
    ranking = "top" if re.search(r"\btop\s*\d+", q) else None
    limit = _top_n(q)
    relation = _relation(q, has_previous_result, dimensions, metrics, outputs, time_grain, ranking, report_sections)
    inherited = []
    if relation == "FOLLOW_UP_ON_PREVIOUS_RESULT":
        inherited = ["table_result"]
    elif relation == "REFINEMENT":
        inherited = ["last_plan", "table_result"]
    reset = [] if relation != "NEW_REQUEST" else ["dimension", "metric", "filter", "time_range", "chart_type", "top_n"]
    commentary = ["three_insights"] if any(term in q for term in ["ba diem", "3 diem", "nhan xet", "noi len", "giai thich"]) else []
    requested_insight_count = _requested_insight_count(q)
    return RequestContract(
        relation_to_previous_turn=relation,
        intent=intent,
        source_file_id=source_file_id,
        dimensions=dimensions,
        metrics=metrics,
        aggregations=aggregations,
        time_grain=time_grain,
        ranking=ranking,
        limit=limit,
        derived_metrics=derived,
        requested_outputs=outputs,
        requested_chart_type=chart_type,
        requested_insight_count=requested_insight_count,
        report_type="downtime" if intent == "report" and ("downtime" in q or "dowtime" in q) else "overview" if intent == "report" else None,
        report_detail_level=_report_detail_level(q) if intent == "report" else None,
        report_sections=report_sections,
        commentary_requirements=commentary,
        inherited_fields=inherited,
        explicitly_reset_fields=reset,
    )


def coverage_for_plan(contract: RequestContract, plan: QueryPlan) -> CoverageResult:
    requested = _contract_requirements(contract)
    planned = _plan_capabilities(plan)
    if contract.requested_insight_count and plan.intent not in {"clarification", "refusal", "safe_failure"}:
        planned.append(f"{contract.requested_insight_count}_insights")
    missing = [item for item in requested if item not in planned]
    return CoverageResult(requested=requested, planned=planned, missing=missing, unexpected=[])


def _relation(
    q: str,
    has_previous_result: bool,
    dimensions: list[str],
    metrics: list[str],
    outputs: list[str],
    time_grain: str | None,
    ranking: str | None,
    report_sections: list[str],
) -> str:
    prior_ref = any(term in q for term in ["ket qua tren", "ket qua vua roi", "bang vua roi", "bang tren", "du lieu tren", "ket qua do"])
    restore_ref = any(term in q for term in ["quay lai", "luc nay", "truoc do", "ban dau", "cau dau tien"])
    complete_new_signal = bool(dimensions or metrics or outputs or time_grain or ranking or report_sections)
    if has_previous_result and restore_ref:
        return "REFINEMENT"
    if prior_ref and has_previous_result and not complete_new_signal:
        return "FOLLOW_UP_ON_PREVIOUS_RESULT"
    if prior_ref and has_previous_result and any(term in q for term in ["them", "bo sung", "voi cung bo loc"]):
        return "REFINEMENT"
    if has_previous_result and _is_context_refinement(q, dimensions, metrics, outputs, time_grain, ranking, report_sections):
        return "REFINEMENT"
    return "NEW_REQUEST"


def _is_context_refinement(
    q: str,
    dimensions: list[str],
    metrics: list[str],
    outputs: list[str],
    time_grain: str | None,
    ranking: str | None,
    report_sections: list[str],
) -> bool:
    if report_sections:
        return False
    word_count = len(q.split())
    has_dimension_or_metric = bool(dimensions or metrics)
    time_only = any(term in q for term in ["chi lay thang", "thang gan nhat", "hai thang gan nhat", "ngay gan nhat", "thang dau tien"])
    output_only = bool(outputs) and not has_dimension_or_metric and not time_grain
    ranking_only = bool(ranking) and not has_dimension_or_metric
    filter_only = any(term in q for term in ["chi lay", "chi giu", "loc", "tren 1 gio", "tren mot gio", "tren 30 phut"]) and not has_dimension_or_metric
    return word_count <= 8 and (time_only or output_only or ranking_only or filter_only)


def _contract_requirements(contract: RequestContract) -> list[str]:
    result: list[str] = []
    result.extend(contract.dimensions)
    result.extend(contract.metrics)
    result.extend(contract.aggregations)
    result.extend(contract.derived_metrics)
    result.extend(contract.requested_outputs)
    result.extend(contract.report_sections)
    if contract.time_grain:
        result.append(f"{contract.time_grain}_time_series")
    if contract.requested_chart_type:
        result.append(f"{contract.requested_chart_type}_chart")
    if contract.requested_insight_count:
        result.append(f"{contract.requested_insight_count}_insights")
    if contract.ranking:
        result.append(contract.ranking)
    return result


def _plan_capabilities(plan: QueryPlan) -> list[str]:
    caps: list[str] = []
    dim_map = {"may": "machine", "machine_name": "machine", "nhom_ton_that": "loss_group", "loss_group": "loss_group", "ten_ton_that": "loss_name", "loss_name": "loss_name", "thoi_gian_bat_dau": "date", "start_time": "date"}
    metric_map = {"total_duration_seconds": "total_downtime", "row_count": "count", "avg_duration_seconds": "average_duration"}
    caps.extend(dim_map.get(dim, dim) for dim in plan.dimensions)
    caps.extend(metric_map.get(metric.name or "", metric.name or metric.aggregation) for metric in plan.metrics)
    caps.extend(metric.aggregation for metric in plan.metrics)
    if any(metric.percentage_of_total for metric in plan.metrics):
        caps.append("percentage")
    if plan.output in {"bar", "horizontal_bar", "line", "pie"}:
        caps.extend(["chart", f"{plan.output}_chart"])
    if plan.output == "report" or plan.intent == "report":
        caps.append("report")
    if plan.time_granularity:
        caps.append(f"{plan.time_granularity}_time_series")
    if plan.sort or plan.ranking:
        caps.append("top")
    return caps


def _is_chart(q: str) -> bool:
    if _negates_chart(q):
        return False
    return any(term in q for term in ["bieu do", "chart", "plot", "bar", "ve cot", "ve line", "ve chart", "ve bieu do"])


def _is_report(q: str) -> bool:
    return any(term in q for term in ["bao cao", "report", "xuat bao cao"])


def _negates_chart(q: str) -> bool:
    return any(
        term in q
        for term in [
            "bo bieu do",
            "bo chart",
            "khong bieu do",
            "khong ve bieu do",
            "khong ve chart",
            "khong can bieu do",
            "khong can chart",
        ]
    )


def _requests_commentary(q: str) -> bool:
    return any(term in q for term in ["nhan xet", "noi len", "giai thich", "diem dang chu y", "quan ly", "insight", "phan tich"])


def _dimensions(q: str) -> list[str]:
    dims = []
    if "may" in q:
        dims.append("machine")
    if "nhom" in q:
        dims.append("loss_group")
    if "nguyen nhan" in q:
        dims.append("loss_name")
    if any(term in q for term in ["theo ngay", "xu huong", "qua thoi gian", "theo thoi gian"]):
        dims.append("date")
    return list(dict.fromkeys(dims))


def _metrics(q: str) -> list[str]:
    metrics = []
    if "downtime" in q or "dowtime" in q or "thoi gian" in q or "thoi luong" in q:
        metrics.append("total_downtime")
    if any(term in q for term in ["so lan", "ghi nhan", "lan dung", "dem"]):
        metrics.append("count")
    if "trung binh" in q:
        metrics.append("average_duration")
    return list(dict.fromkeys(metrics))


def _aggregations(q: str) -> list[str]:
    aggs = []
    if "tong" in q or "downtime" in q or "dowtime" in q:
        aggs.append("sum")
    if any(term in q for term in ["so lan", "ghi nhan", "dem"]):
        aggs.append("count")
    if "trung binh" in q:
        aggs.append("avg")
    return list(dict.fromkeys(aggs))


def _requested_chart_type(q: str) -> str | None:
    if any(term in q for term in ["xu huong", "theo ngay", "theo thang", "qua thoi gian", "line"]):
        return "line"
    if "top" in q or any(term in q for term in ["cao nhat", "nhieu nhat", "pho bien nhat"]):
        return "bar"
    if any(term in q for term in ["phan bo", "ty le", "co cau", "pie", "tron"]):
        return "pie"
    if any(term in q for term in ["top", "cot", "bar"]):
        return "bar"
    return "bar"


def _report_sections(q: str) -> list[str]:
    if "downtime" in q or "dowtime" in q:
        return ["dataset_overview", "kpi_total_downtime", "kpi_stop_count", "top_machines", "top_causes", "time_trend", "management_commentary", "source_filters_limitations"]
    sections = ["dataset_overview", "record_count", "date_range", "three_insights", "top_5_table", "chart", "source", "limitations"]
    return sections


def _time_grain(q: str) -> str | None:
    if "theo ngay" in q or "daily" in q:
        return "day"
    if "xu huong" in q or "qua thoi gian" in q or "theo thoi gian" in q:
        return "day"
    if "theo thang" in q or "monthly" in q:
        return "month"
    if "theo tuan" in q:
        return "week"
    return None


def _top_n(q: str) -> int | None:
    match = re.search(r"\btop\s*(\d{1,2})", q)
    return int(match.group(1)) if match else None


def _requested_insight_count(q: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\s*(?:diem|insight|nhan xet)", q)
    if match:
        return max(1, min(int(match.group(1)), 10))
    if "hai diem" in q or "2 nhan xet" in q:
        return 2
    if "ba diem" in q or "3 nhan xet" in q:
        return 3
    return None


def _report_detail_level(q: str) -> str | None:
    if any(term in q for term in ["rut gon", "ngan gon", "compact"]):
        return "COMPACT"
    if any(term in q for term in ["chi tiet", "day du", "sau hon"]):
        return "DETAILED"
    return "STANDARD"
