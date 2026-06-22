from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Intent = Literal["query", "chart", "dashboard", "report", "clarification", "refusal", "safe_failure"]
OutputKind = Literal["text", "table", "bar", "horizontal_bar", "line", "pie", "dashboard", "report"]
Operator = Literal[
    "equals",
    "not_equals",
    "contains",
    "in",
    "greater_than",
    "greater_or_equal",
    "less_than",
    "less_or_equal",
    "between",
    "date_between",
    "is_null",
    "is_not_null",
]
Aggregation = Literal["count", "count_distinct", "sum", "avg", "min", "max", "median"]


class FilterSpec(BaseModel):
    column: str
    operator: Operator
    value: Any = None


class MetricSpec(BaseModel):
    name: str | None = None
    alias: str | None = None
    aggregation: Aggregation
    column: str | None = None
    percentage_of_total: bool = False

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "MetricSpec":
        if self.alias and not self.name:
            self.name = self.alias
        if self.name and not self.alias:
            self.alias = self.name
        if self.aggregation not in {"count"} and not self.column:
            raise ValueError("column is required for this aggregation")
        return self


class SortSpec(BaseModel):
    column: str = ""
    field: str | None = None
    direction: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def normalize_field(self) -> "SortSpec":
        if self.field and not self.column:
            self.column = self.field
        if self.column and not self.field:
            self.field = self.column
        return self


class JoinSpec(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    type: Literal["inner", "left"] = "inner"


class HavingCondition(BaseModel):
    metric_alias: str
    operator: Literal["greater_than", "greater_or_equal", "less_than", "less_or_equal"]
    comparison: Literal["constant", "group_average", "overall_average"]
    value: float | None = None


class RankingSpec(BaseModel):
    partition_by: list[str] = Field(default_factory=list)
    order_by: str
    direction: Literal["asc", "desc"] = "desc"
    rank_type: Literal["row_number", "rank", "dense_rank"] = "row_number"
    top_n: int | None = Field(default=None, ge=1, le=100)


class DerivedMetric(BaseModel):
    alias: str
    expression_type: Literal["difference", "percentage_change", "ratio", "share_of_total"]
    left_metric: str
    right_metric: str | None = None


class QueryPlan(BaseModel):
    intent: Intent = "query"
    tables: list[str] = Field(default_factory=list)
    joins: list[JoinSpec] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[MetricSpec] = Field(default_factory=list)
    having: list[HavingCondition] = Field(default_factory=list)
    ranking: RankingSpec | None = None
    derived_metrics: list[DerivedMetric] = Field(default_factory=list)
    time_comparison: dict | None = None
    time_granularity: Literal["day", "week", "month", "year"] | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=500)
    output: OutputKind = "table"
    query_complexity: Literal["simple", "complex"] = "simple"
    clarification_question: str | None = None
