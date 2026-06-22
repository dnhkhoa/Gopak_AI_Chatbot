from __future__ import annotations

import pandas as pd
import plotly.express as px

from src.query.schemas import QueryPlan
from src.rendering.formatters import humanize_column_name


def build_chart(df: pd.DataFrame, plan: QueryPlan, catalog: dict | None = None):
    if df.empty or len(df.columns) < 2:
        return None
    x = plan.dimensions[0] if plan.dimensions and plan.dimensions[0] in df.columns else df.columns[0]
    y_candidates = [metric.name or f"{metric.aggregation}_{metric.column}" for metric in plan.metrics]
    y = next((col for col in y_candidates if col in df.columns), df.columns[-1])
    data = df.copy()
    labels = {x: humanize_column_name(x, catalog), y: humanize_column_name(y, catalog)}
    if plan.output in {"bar", "horizontal_bar"}:
        data = data.head(15)
        if plan.output == "horizontal_bar":
            fig = px.bar(data, x=y, y=x, orientation="h", title="Kết quả phân tích", labels=labels)
        else:
            fig = px.bar(data, x=x, y=y, title="Kết quả phân tích", labels=labels)
        fig.update_layout(margin=dict(l=10, r=10, t=56, b=10))
        return fig
    if plan.output == "line":
        fig = px.line(data.sort_values(x), x=x, y=y, markers=True, title="Xu hướng theo thời gian", labels=labels)
        fig.update_layout(margin=dict(l=10, r=10, t=56, b=10))
        return fig
    if plan.output == "pie":
        fig = px.pie(data.head(15), names=x, values=y, title="Tỷ trọng", labels=labels)
        fig.update_layout(margin=dict(l=10, r=10, t=56, b=10))
        return fig
    return None


def chart_spec_valid(df: pd.DataFrame, plan: QueryPlan) -> bool:
    if plan.output not in {"bar", "horizontal_bar", "line", "pie"}:
        return True
    return not df.empty and bool(plan.dimensions) and bool(plan.metrics)

