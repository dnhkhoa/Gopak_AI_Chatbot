from __future__ import annotations

from src.query.schemas import QueryPlan


class PlanValidationError(ValueError):
    pass


class PlanValidator:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.tables = {table["table_name"]: table for table in catalog.get("tables", [])}

    def validate(self, plan: QueryPlan) -> QueryPlan:
        if plan.intent in {"clarification", "refusal", "safe_failure"}:
            return plan
        if not plan.tables:
            raise PlanValidationError("Plan must include at least one table.")
        if len(plan.tables) > 1 and not plan.joins and plan.execution_strategy != "parallel_queries_then_merge":
            raise PlanValidationError("Multi-table plans require explicit joins or a parallel_queries_then_merge execution strategy.")
        if plan.execution_strategy == "parallel_queries_then_merge":
            raise PlanValidationError("Parallel multi-source plans must be executed by the production execution planner, not the single SQL builder.")
        for table in plan.tables:
            if table not in self.tables:
                raise PlanValidationError(f"Unknown table: {table}")
        allowed_columns = self._allowed_columns(plan)
        metric_aliases = {metric.name for metric in plan.metrics if metric.name} | {metric.alias for metric in plan.metrics if getattr(metric, "alias", None)}
        for column in list(plan.dimensions) + [f.column for f in plan.filters]:
            self._assert_column(column, allowed_columns)
        for flt in plan.filters:
            self._assert_filter_type(flt.column, flt.operator, plan)
        for sort in plan.sort:
            if sort.column not in allowed_columns and sort.column not in metric_aliases:
                raise PlanValidationError(f"Unknown sort field: {sort.column}")
        for having in plan.having:
            if having.metric_alias not in metric_aliases:
                raise PlanValidationError(f"Unknown having metric: {having.metric_alias}")
            if having.comparison == "constant" and having.value is None:
                raise PlanValidationError("Constant having comparison requires a value.")
        if plan.ranking:
            for column in plan.ranking.partition_by:
                self._assert_column(column, allowed_columns)
            if plan.ranking.order_by not in metric_aliases and plan.ranking.order_by not in allowed_columns:
                raise PlanValidationError(f"Unknown ranking order field: {plan.ranking.order_by}")
        for metric in plan.derived_metrics:
            if metric.left_metric not in metric_aliases:
                raise PlanValidationError(f"Unknown derived metric left operand: {metric.left_metric}")
            if metric.right_metric and metric.right_metric not in metric_aliases:
                raise PlanValidationError(f"Unknown derived metric right operand: {metric.right_metric}")
        for metric in plan.metrics:
            if metric.column:
                self._assert_column(metric.column, allowed_columns)
                self._assert_aggregation_type(metric.aggregation, metric.column, plan)
        for join in plan.joins:
            if join.left_table not in plan.tables or join.right_table not in plan.tables:
                raise PlanValidationError("Join table must be present in plan tables.")
            self._assert_column(join.left_column, self._table_columns(join.left_table))
            self._assert_column(join.right_column, self._table_columns(join.right_table))
            if not self._relationship_allowed(join):
                raise PlanValidationError(f"Join is not supported by catalog evidence: {join.left_table}.{join.left_column} -> {join.right_table}.{join.right_column}")
        if plan.limit and plan.limit < 20 and plan.metrics and not plan.dimensions and not plan.ranking:
            raise PlanValidationError("Top-N style plans require at least one dimension.")
        return plan

    def _table_columns(self, table_name: str) -> set[str]:
        return {column["normalized_name"] for column in self.tables[table_name].get("columns", [])}

    def _allowed_columns(self, plan: QueryPlan) -> set[str]:
        columns: set[str] = set()
        for table in plan.tables:
            columns |= self._table_columns(table)
        return columns

    def _assert_column(self, column: str, allowed_columns: set[str]) -> None:
        if column not in allowed_columns:
            raise PlanValidationError(f"Unknown column: {column}")

    def _relationship_allowed(self, join) -> bool:
        for rel in self.catalog.get("relationships", []):
            if (
                rel["left_table"] == join.left_table
                and rel["left_column"] == join.left_column
                and rel["right_table"] == join.right_table
                and rel["right_column"] == join.right_column
                and rel["confidence"] >= 0.65
            ):
                return True
        return False

    def _assert_aggregation_type(self, aggregation: str, column: str, plan: QueryPlan) -> None:
        if aggregation in {"sum", "avg", "median"}:
            for table in plan.tables:
                for item in self.tables[table].get("columns", []):
                    if item["normalized_name"] == column:
                        dtype = str(item.get("dtype", ""))
                        role = item.get("semantic_role")
                        if not (dtype.startswith(("int", "float")) or role in {"duration_seconds"}):
                            raise PlanValidationError(f"Aggregation {aggregation} requires numeric/duration column: {column}")

    def _column_metadata(self, column: str, plan: QueryPlan) -> dict | None:
        for table in plan.tables:
            for item in self.tables[table].get("columns", []):
                if item["normalized_name"] == column:
                    return item
        return None

    def _assert_filter_type(self, column: str, operator: str, plan: QueryPlan) -> None:
        item = self._column_metadata(column, plan)
        if not item:
            return
        dtype = str(item.get("dtype", ""))
        role = item.get("semantic_role")
        if operator == "date_between" and "datetime" not in dtype and role not in {"start_time", "end_time"}:
            raise PlanValidationError(f"Date filter requires date/datetime column: {column}")
        if operator in {"greater_than", "greater_or_equal", "less_than", "less_or_equal", "between"}:
            if not (dtype.startswith(("int", "float")) or "datetime" in dtype or role in {"duration_seconds", "start_time", "end_time"}):
                raise PlanValidationError(f"Range filter requires numeric/date column: {column}")
