from __future__ import annotations

import math

import pandas as pd

from src.query.schemas import QueryPlan


class ResultValidationError(ValueError):
    pass


class ResultValidator:
    def validate(self, df: pd.DataFrame, plan: QueryPlan) -> pd.DataFrame:
        if plan.intent in {"clarification", "refusal", "safe_failure"}:
            raise ResultValidationError("Non-executable plan must not return a result.")
        for column in df.select_dtypes(include=["float", "int"]).columns:
            values = df[column].dropna().tolist()
            if any(isinstance(value, float) and not math.isfinite(value) for value in values):
                raise ResultValidationError(f"Non-finite numeric value in result column: {column}")
        if plan.output in {"bar", "horizontal_bar", "line", "pie"}:
            if plan.dimensions and plan.dimensions[0] not in df.columns:
                raise ResultValidationError("Chart dimension is missing from result.")
            metric_names = [metric.name or f"{metric.aggregation}_{metric.column}" for metric in plan.metrics]
            if metric_names and not any(name in df.columns for name in metric_names):
                raise ResultValidationError("Chart metric is missing from result.")
        if plan.sort and len(df) > 1 and not plan.ranking:
            sort = plan.sort[0]
            if sort.column in df.columns and pd.api.types.is_numeric_dtype(df[sort.column]):
                ordered = df[sort.column].is_monotonic_decreasing if sort.direction == "desc" else df[sort.column].is_monotonic_increasing
                if not ordered:
                    raise ResultValidationError(f"Result is not sorted by {sort.column} {sort.direction}.")
        if plan.ranking and plan.ranking.top_n:
            rank_column = "_rank"
            if rank_column in df.columns and (df[rank_column] > plan.ranking.top_n).any():
                raise ResultValidationError("Windowed ranking result exceeded requested per-partition top N.")
        elif plan.limit and len(df) > plan.limit:
            raise ResultValidationError("Result exceeded requested limit.")
        return df
