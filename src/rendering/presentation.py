from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from src.query.schemas import QueryPlan
from src.rendering.formatters import (
    format_dataframe_for_display,
    format_duration,
    format_vn_number,
    humanize_column_name,
    is_duration_column,
    short_source_name,
)


class PresentedResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    response_type: Literal["scalar", "table", "chart", "dashboard", "report", "clarification", "error"]
    title: str
    summary: str
    primary_value: str | None = None
    secondary_value: str | None = None
    result_dataframe: Any | None = None
    raw_dataframe: Any | None = None
    chart: Any | None = None
    source_text: str | None = None
    filter_text: str | None = None


def build_presented_response(
    question: str,
    plan: QueryPlan,
    df: pd.DataFrame,
    catalog: dict,
    sources: list[dict],
    chart: Any | None = None,
) -> PresentedResponse:
    if plan.intent in {"clarification", "refusal", "safe_failure"}:
        is_clarification = plan.intent == "clarification"
        return PresentedResponse(
            response_type="clarification" if is_clarification else "error",
            title="Cần làm rõ" if plan.intent == "clarification" else "Không thể truy vấn an toàn",
            summary=plan.clarification_question or "Bạn muốn phân tích theo bảng, cột hoặc khoảng thời gian nào?",
        )
    if df.empty:
        return PresentedResponse(
            response_type="table",
            title="Không có dữ liệu",
            summary="Không tìm thấy dữ liệu phù hợp với điều kiện đã chọn.",
            result_dataframe=format_dataframe_for_display(df, catalog),
            raw_dataframe=df,
            source_text=_source_text(sources),
            filter_text=_filter_text(plan, catalog),
        )
    if _is_scalar(df, plan):
        column = df.columns[0]
        value = df.iloc[0, 0]
        title = humanize_column_name(column, catalog)
        if is_duration_column(column):
            duration = format_duration(value)
            return PresentedResponse(
                response_type="scalar",
                title=title,
                summary=f"Tương đương {duration['secondary']}." if duration["secondary"] else "",
                primary_value=duration["primary"],
                secondary_value=duration["secondary"],
                raw_dataframe=df,
                source_text=_source_text(sources),
                filter_text=_filter_text(plan, catalog),
            )
        return PresentedResponse(
            response_type="scalar",
            title=title,
            summary="",
            primary_value=format_vn_number(value, 2),
            raw_dataframe=df,
            source_text=_source_text(sources),
            filter_text=_filter_text(plan, catalog),
        )

    display_df = format_dataframe_for_display(df, catalog)
    response_type = "chart" if plan.output in {"bar", "horizontal_bar", "line", "pie"} else plan.intent
    if response_type not in {"chart", "dashboard", "report"}:
        response_type = "table"
    return PresentedResponse(
        response_type=response_type,
        title=_result_title(plan, catalog),
        summary=_table_summary(df, plan, catalog),
        result_dataframe=display_df,
        raw_dataframe=df,
        chart=chart,
        source_text=_source_text(sources),
        filter_text=_filter_text(plan, catalog),
    )


def should_show_download_button(path: Path | None) -> bool:
    return bool(path and path.exists())


def _is_scalar(df: pd.DataFrame, plan: QueryPlan) -> bool:
    return len(df) == 1 and len(df.columns) == 1 and bool(plan.metrics)


def _result_title(plan: QueryPlan, catalog: dict) -> str:
    if plan.intent == "dashboard":
        return "Dashboard tổng quan"
    if plan.intent == "report":
        return "Báo cáo phân tích"
    if plan.output in {"bar", "horizontal_bar", "line", "pie"}:
        return "Biểu đồ phân tích"
    if plan.dimensions:
        return f"Phân tích theo {humanize_column_name(plan.dimensions[0], catalog).lower()}"
    return "Kết quả phân tích"


def _table_summary(df: pd.DataFrame, plan: QueryPlan, catalog: dict) -> str:
    if df.empty:
        return "Không tìm thấy dữ liệu phù hợp với điều kiện đã chọn."
    if not plan.metrics and plan.dimensions and plan.dimensions[0] in df.columns:
        dim_col = plan.dimensions[0]
        dim_name = humanize_column_name(dim_col, catalog).lower()
        values = [str(value) for value in df[dim_col].dropna().unique().tolist()]
        total = len(values)
        shown = ", ".join(values[:8])
        more = f" (và {format_vn_number(total - 8, 0)} giá trị khác)" if total > 8 else ""
        return f"Có {format_vn_number(total, 0)} {dim_name}: {shown}{more}."
    metric_aliases = [metric.name or f"{metric.aggregation}_{metric.column}" for metric in plan.metrics]
    metric_col = next((column for column in metric_aliases if column in df.columns), df.columns[-1])
    dimension_col = plan.dimensions[0] if plan.dimensions and plan.dimensions[0] in df.columns else df.columns[0]
    if metric_col in df.columns and dimension_col in df.columns:
        top = df.iloc[0]
        label = top[dimension_col]
        value = top[metric_col]
        metric_name = humanize_column_name(metric_col, catalog).lower()
        formatted = format_duration(value)["primary"] if is_duration_column(metric_col) else format_vn_number(value, 2)
        return f"{label} có {metric_name} cao nhất: {formatted}."
    return f"Có {format_vn_number(len(df), 0)} dòng kết quả phù hợp."


def _source_text(sources: list[dict]) -> str | None:
    if not sources:
        return None
    source_names = [short_source_name(str(item.get("source", ""))) for item in sources]
    return "Nguồn: " + "; ".join(source_names)


def _filter_text(plan: QueryPlan, catalog: dict) -> str | None:
    if not plan.filters:
        return "Bộ lọc: không có"
    parts = []
    for item in plan.filters:
        name = humanize_column_name(item.column, catalog)
        parts.append(f"{name} {item.operator} {item.value}")
    return "Bộ lọc: " + "; ".join(parts)
