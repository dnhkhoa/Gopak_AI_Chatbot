from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field


class ConversationState(BaseModel):
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))

    active_table: str | None = None
    active_metric: dict | None = None
    active_metrics: list[dict] = Field(default_factory=list)
    active_dimensions: list[str] = Field(default_factory=list)
    active_filters: list[dict] = Field(default_factory=list)
    active_time_range: dict | list[str] | None = None
    active_having: list[dict] = Field(default_factory=list)
    active_ranking: dict | None = None
    active_sort: list[dict] = Field(default_factory=list)
    active_limit: int | None = None
    active_output: str = "text"

    last_entities: dict[str, object] = Field(default_factory=dict)
    last_result_summary: dict | None = None
    last_result_cache_id: str | None = None
    last_result_reference: dict | None = None
    last_plan: dict | None = None

    recent_turn_ids: list[str] = Field(default_factory=list)
    conversation_summary: str | None = None

    # Compatibility aliases used by earlier planner/evaluation code.
    active_tables: list[str] = Field(default_factory=list)
    time_range: list[str] | None = None
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[dict] = Field(default_factory=list)
    last_output: str | None = None

    def update_from_plan(self, plan, output: str | None = None) -> None:
        if getattr(plan, "tables", None):
            self.active_tables = list(plan.tables)
            self.active_table = plan.tables[0]
        if getattr(plan, "filters", None):
            self.active_filters = [f.model_dump() for f in plan.filters]
            for flt in plan.filters:
                if flt.column and flt.value:
                    self.last_entities[flt.column] = flt.value
                if flt.operator == "date_between":
                    self.active_time_range = {"column": flt.column, "value": list(flt.value)}
                    self.time_range = list(flt.value)
        if getattr(plan, "dimensions", None):
            self.dimensions = list(plan.dimensions)
            self.active_dimensions = list(plan.dimensions)
        if getattr(plan, "metrics", None):
            self.metrics = [m.model_dump() for m in plan.metrics]
            self.active_metrics = list(self.metrics)
            self.active_metric = self.metrics[0] if self.metrics else None
        if getattr(plan, "having", None):
            self.active_having = [h.model_dump() for h in plan.having]
        if getattr(plan, "ranking", None):
            self.active_ranking = plan.ranking.model_dump() if plan.ranking else None
        if getattr(plan, "sort", None):
            self.active_sort = [s.model_dump() for s in plan.sort]
        if getattr(plan, "limit", None):
            self.active_limit = int(plan.limit)
        if output:
            self.last_output = output
            self.active_output = output
        self.last_plan = plan.model_dump() if hasattr(plan, "model_dump") else None

    def update_from_result(self, df) -> None:
        if df is None or getattr(df, "empty", True):
            self.last_result_summary = {"row_count": 0, "columns": []}
            return
        first = df.iloc[0].to_dict()
        self.last_result_summary = {
            "row_count": int(len(df)),
            "columns": [str(col) for col in df.columns],
            "first_row": first,
        }
        if "may" in first:
            self.last_entities["top_machine"] = first["may"]
        if "ten_ton_that" in first:
            self.last_entities["top_loss_name"] = first["ten_ton_that"]
        if "nhom_ton_that" in first:
            self.last_entities["top_group"] = first["nhom_ton_that"]

    def to_prompt_dict(self) -> dict:
        return self.model_dump()

    def reset(self) -> None:
        conversation_id = self.conversation_id
        recent_turn_ids = list(self.recent_turn_ids)
        self.__dict__.update(ConversationState(conversation_id=conversation_id, recent_turn_ids=recent_turn_ids).model_dump())
