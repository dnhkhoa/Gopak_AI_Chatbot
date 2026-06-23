from __future__ import annotations

from dataclasses import dataclass, field

from src.config import Settings
from src.conversation.reference_resolver import resolve_reference
from src.conversation.state import ConversationState
from src.conversation.turn_classifier import TurnType, classify_turn
from src.query.schemas import FilterSpec, MetricSpec, QueryPlan, SortSpec
from src.query_understanding.catalog_utils import find_table, role_column
from src.query_understanding.filter_parser import duration_threshold, parse_filters
from src.query_understanding.text import normalize_text
from src.query_understanding.time_resolver import resolve_time
from src.query_understanding.topn_detector import detect_topn


@dataclass
class MergeResult:
    plan: QueryPlan | None
    turn_type: str
    confidence: float
    changes: dict = field(default_factory=dict)
    reason: str = ""


class StateMerger:
    def __init__(self, catalog: dict, settings: Settings):
        self.catalog = catalog
        self.settings = settings

    def merge(self, question: str, state: ConversationState) -> MergeResult:
        has_state = bool(state.last_plan and state.active_table)
        classification = classify_turn(question, has_state)
        if classification.turn_type in {TurnType.REFERENCE_ENTITY, TurnType.REFERENCE_RESULT} and not has_state:
            return MergeResult(None, classification.turn_type.value, classification.confidence, reason="Reference phrase has no active structured state.")
        if classification.turn_type == TurnType.NEW_QUERY or not has_state:
            return MergeResult(None, classification.turn_type.value, classification.confidence, reason=classification.reason)
        if classification.turn_type == TurnType.RESET_CONTEXT:
            state.reset()
            return MergeResult(None, classification.turn_type.value, classification.confidence, {"reset": True}, classification.reason)

        try:
            plan = QueryPlan.model_validate(state.last_plan)
        except Exception:
            return MergeResult(None, classification.turn_type.value, 0.0, reason="No valid previous plan to merge.")

        table = self._active_table(plan, state)
        if not table:
            return MergeResult(None, classification.turn_type.value, 0.0, reason="No active table.")

        q = normalize_text(question)
        duration = role_column(table, "duration_seconds")
        machine = role_column(table, "machine")
        start_time = role_column(table, "start_time")
        loss_name = role_column(table, "loss_name")
        loss_group = role_column(table, "loss_group")
        changes: dict = {}

        if classification.turn_type == TurnType.CHANGE_TIME:
            time = resolve_time(question, table, start_time)
            if not time.filters:
                return MergeResult(None, classification.turn_type.value, 0.40, reason="Could not resolve time reference.")
            plan.filters = self._replace_filter_columns(plan.filters, [flt.column for flt in time.filters], time.filters)
            changes["time_filters"] = [flt.model_dump() for flt in time.filters]

        elif classification.turn_type == TurnType.ADD_FILTER:
            parsed = parse_filters(question, table, machine, loss_group, loss_name, duration, None)
            new_filters = parsed.value
            if not new_filters and duration and duration_threshold(q) is not None:
                new_filters = [FilterSpec(column=duration, operator="greater_than", value=duration_threshold(q))]
            if not new_filters:
                return MergeResult(None, classification.turn_type.value, 0.40, reason="Could not resolve filter.")
            plan.filters = self._replace_filter_columns(plan.filters, [flt.column for flt in new_filters], new_filters)
            changes["filters"] = [flt.model_dump() for flt in new_filters]

        elif classification.turn_type == TurnType.REMOVE_FILTER:
            plan.filters = []
            changes["filters"] = []

        elif classification.turn_type in {TurnType.CHANGE_OUTPUT, TurnType.CHANGE_RANKING, TurnType.REFINE_PREVIOUS}:
            self._apply_output(question, plan)
            topn = detect_topn(question)
            if topn.value:
                plan.limit = int(topn.value["limit"])
                if plan.metrics:
                    plan.sort = [SortSpec(column=plan.metrics[0].name or "row_count", direction=topn.value["direction"])]
                changes["ranking"] = {"limit": plan.limit, "sort": [sort.model_dump() for sort in plan.sort]}
            changes["output"] = plan.output

        elif classification.turn_type == TurnType.CHANGE_METRIC:
            metrics = self._metrics_from_question(q, duration)
            if metrics:
                plan.metrics = metrics
                plan.sort = [SortSpec(column=metrics[0].name or "row_count", direction="desc")] if plan.dimensions else []
                changes["metrics"] = [metric.model_dump() for metric in metrics]

        elif classification.turn_type == TurnType.CHANGE_DIMENSION:
            dimension = self._dimension_from_question(q, machine, loss_name, loss_group, start_time)
            if dimension:
                plan.dimensions = [dimension]
                changes["dimensions"] = [dimension]

        elif classification.turn_type in {TurnType.REFERENCE_ENTITY, TurnType.REFERENCE_RESULT}:
            reference = resolve_reference(question, state)
            if not reference:
                return MergeResult(None, classification.turn_type.value, 0.35, reason="Missing structured reference.")
            if reference.entity_type == "machine":
                plan.filters = self._replace_filter_columns(plan.filters, [machine], [FilterSpec(column=machine, operator="equals", value=reference.value)])
                if "nguyen nhan" in q and loss_name:
                    plan.dimensions = [loss_name]
                    plan.metrics = [MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")]
                    topn = detect_topn(question)
                    plan.limit = int(topn.value["limit"]) if topn.value else 3
                    plan.sort = [SortSpec(column="total_duration_seconds", direction="desc")]
            elif reference.entity_type == "loss_name":
                plan.filters = self._replace_filter_columns(plan.filters, [loss_name], [FilterSpec(column=loss_name, operator="equals", value=reference.value)])
                if "may" in q and machine:
                    plan.dimensions = [machine]
                    plan.metrics = [MetricSpec(aggregation="count", column=None, name="row_count")]
                    plan.sort = [SortSpec(column="row_count", direction="desc")]
                    plan.limit = 1
            elif reference.entity_type == "loss_group":
                plan.filters = self._replace_filter_columns(plan.filters, [loss_group], [FilterSpec(column=loss_group, operator="equals", value=reference.value)])
                if "nguyen nhan" in q and loss_name:
                    plan.dimensions = [loss_name]
                    plan.metrics = [MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")]
                    plan.sort = [SortSpec(column="total_duration_seconds", direction="desc")]
            changes["reference"] = reference.__dict__

        else:
            return MergeResult(None, classification.turn_type.value, 0.0, reason="Unsupported merge type.")

        plan.query_complexity = "simple"
        return MergeResult(plan, classification.turn_type.value, classification.confidence, changes, classification.reason)

    def _active_table(self, plan: QueryPlan, state: ConversationState) -> dict | None:
        table_name = plan.tables[0] if plan.tables else state.active_table
        if table_name:
            return next((table for table in self.catalog.get("tables", []) if table["table_name"] == table_name), None)
        scoped_tables = self.catalog.get("tables", [])
        return find_table(self.catalog, "machine_downtime") or (scoped_tables[0] if len(scoped_tables) == 1 else None)

    def _replace_filter_columns(self, old: list[FilterSpec], columns: list[str | None], new: list[FilterSpec]) -> list[FilterSpec]:
        column_set = {col for col in columns if col}
        kept = [flt for flt in old if flt.column not in column_set]
        return kept + [flt for flt in new if flt.column]

    def _apply_output(self, question: str, plan: QueryPlan) -> None:
        q = normalize_text(question)
        if "dashboard" in q:
            plan.intent = "dashboard"
            plan.output = "dashboard"
        elif "bao cao" in q or "excel" in q or any(term in q for term in ["xuat excel", "xuat file", "xuat bao cao", "xuat ket qua", "xuat ra"]):
            plan.intent = "report"
            plan.output = "report"
        elif "pie" in q or "tron" in q:
            plan.intent = "chart"
            plan.output = "pie"
        elif "ve" in q or "bieu do" in q or "chart" in q:
            plan.intent = "chart"
            plan.output = "bar"

    def _metrics_from_question(self, q: str, duration: str | None) -> list[MetricSpec]:
        if any(term in q for term in ["ty le", "phan tram", "ty trong"]):
            return [MetricSpec(aggregation="count", column=None, name="row_count", percentage_of_total=True)]
        if any(term in q for term in ["tong", "downtime"]):
            return [MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")]
        if any(term in q for term in ["so lan", "dem"]):
            return [MetricSpec(aggregation="count", column=None, name="row_count")]
        if "trung binh" in q:
            return [MetricSpec(aggregation="avg", column=duration, name="avg_duration_seconds")]
        return []

    def _dimension_from_question(
        self,
        q: str,
        machine: str | None,
        loss_name: str | None,
        loss_group: str | None,
        start_time: str | None,
    ) -> str | None:
        if "may" in q:
            return machine
        if "nguyen nhan" in q:
            return loss_name
        if "nhom" in q:
            return loss_group
        if "ngay" in q or "thang" in q:
            return start_time
        return None
