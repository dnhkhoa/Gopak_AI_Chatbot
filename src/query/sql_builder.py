from __future__ import annotations

from typing import Any

from src.query.schemas import QueryPlan


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class SQLBuilder:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.tables = {table["table_name"]: table for table in catalog.get("tables", [])}

    def build(self, plan: QueryPlan) -> tuple[str, list[Any]]:
        if self._needs_cte(plan):
            return self._build_cte(plan)
        return self._build_simple(plan)

    def _build_simple(self, plan: QueryPlan) -> tuple[str, list[Any]]:
        base_table = plan.tables[0]
        from_clause, params = self._from_clause(plan)
        select_parts, group_parts = self._aggregate_parts(plan)
        if not select_parts:
            select_parts = [f"{quote_ident(base_table)}.*"]

        where_parts, where_params = self._where_parts(plan)
        params.extend(where_params)

        sql = f"SELECT {', '.join(select_parts)} FROM {from_clause}"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        if group_parts:
            sql += " GROUP BY " + ", ".join(group_parts)
        if plan.sort:
            sorts = [f"{quote_ident(sort.column)} {sort.direction.upper()}" for sort in plan.sort]
            sql += " ORDER BY " + ", ".join(sorts)
        elif group_parts and plan.time_granularity:
            first_dimension = plan.dimensions[0]
            sql += f" ORDER BY {quote_ident(first_dimension)} ASC"
        elif plan.metrics and select_parts:
            metric_alias = plan.metrics[0].name or (f"{plan.metrics[0].aggregation}_{plan.metrics[0].column}" if plan.metrics[0].column else "row_count")
            sql += f" ORDER BY {quote_ident(metric_alias)} DESC"
        sql += f" LIMIT {int(plan.limit)}"
        return sql, params

    def _build_cte(self, plan: QueryPlan) -> tuple[str, list[Any]]:
        from_clause, params = self._from_clause(plan)
        select_parts, group_parts = self._aggregate_parts(plan)
        where_parts, where_params = self._where_parts(plan)
        params.extend(where_params)
        base_sql = f"SELECT {', '.join(select_parts)} FROM {from_clause}"
        if where_parts:
            base_sql += " WHERE " + " AND ".join(where_parts)
        if group_parts:
            base_sql += " GROUP BY " + ", ".join(group_parts)

        base_columns = [*plan.dimensions, *[self._metric_name(metric) for metric in plan.metrics]]
        outer_select = [quote_ident(column) for column in base_columns]
        for metric in plan.metrics:
            metric_name = self._metric_name(metric)
            if metric.percentage_of_total:
                alias = "percentage"
                outer_select.append(
                    f"CASE WHEN SUM({quote_ident(metric_name)}) OVER () = 0 THEN NULL "
                    f"ELSE ({quote_ident(metric_name)} * 100.0 / NULLIF(SUM({quote_ident(metric_name)}) OVER (), 0)) END AS {quote_ident(alias)}"
                )
        for derived in plan.derived_metrics:
            if derived.expression_type == "share_of_total":
                outer_select.append(
                    f"CASE WHEN SUM({quote_ident(derived.left_metric)}) OVER () = 0 THEN NULL "
                    f"ELSE ({quote_ident(derived.left_metric)} * 100.0 / NULLIF(SUM({quote_ident(derived.left_metric)}) OVER (), 0)) END AS {quote_ident(derived.alias)}"
                )

        outer_sql = f"SELECT {', '.join(outer_select)} FROM base"
        having_parts = [self._having_clause(item) for item in plan.having]
        if having_parts:
            outer_sql += " WHERE " + " AND ".join(having_parts)

        if plan.ranking:
            partition = ", ".join(quote_ident(col) for col in plan.ranking.partition_by)
            partition_sql = f"PARTITION BY {partition} " if partition else ""
            rank_fn = plan.ranking.rank_type.upper()
            ranked_sql = (
                "WITH base AS ("
                + base_sql
                + "), filtered AS ("
                + outer_sql
                + "), ranked AS (SELECT *, "
                + f"{rank_fn}() OVER ({partition_sql}ORDER BY {quote_ident(plan.ranking.order_by)} {plan.ranking.direction.upper()}) AS {quote_ident('_rank')} FROM filtered)"
            )
            sql = ranked_sql + " SELECT * FROM ranked"
            if plan.ranking.top_n:
                sql += f" WHERE {quote_ident('_rank')} <= {int(plan.ranking.top_n)}"
            if plan.ranking.partition_by:
                order_cols = ", ".join(f"{quote_ident(col)} ASC" for col in plan.ranking.partition_by)
                sql += f" ORDER BY {order_cols}, {quote_ident('_rank')} ASC"
            else:
                sql += f" ORDER BY {quote_ident('_rank')} ASC"
            return sql, params

        sql = "WITH base AS (" + base_sql + ") " + outer_sql
        if plan.sort:
            sorts = [f"{quote_ident(sort.column)} {sort.direction.upper()}" for sort in plan.sort]
            sql += " ORDER BY " + ", ".join(sorts)
        sql += f" LIMIT {int(plan.limit)}"
        return sql, params

    def _needs_cte(self, plan: QueryPlan) -> bool:
        return bool(plan.having or plan.ranking or plan.derived_metrics or any(metric.percentage_of_total for metric in plan.metrics))

    def _from_clause(self, plan: QueryPlan) -> tuple[str, list[Any]]:
        base_table = plan.tables[0]
        from_clause = f"read_parquet(?) AS {quote_ident(base_table)}"
        params: list[Any] = [self.tables[base_table]["parquet_path"]]
        for join in plan.joins:
            right_path = self.tables[join.right_table]["parquet_path"]
            from_clause += (
                f" {join.type.upper()} JOIN read_parquet(?) AS {quote_ident(join.right_table)}"
                f" ON {quote_ident(join.left_table)}.{quote_ident(join.left_column)} = {quote_ident(join.right_table)}.{quote_ident(join.right_column)}"
            )
            params.append(right_path)
        return from_clause, params

    def _aggregate_parts(self, plan: QueryPlan) -> tuple[list[str], list[str]]:
        select_parts: list[str] = []
        group_parts: list[str] = []
        for dimension in plan.dimensions:
            expr = self._column_expr(dimension, plan)
            if plan.time_granularity and self._is_time_column(dimension, plan):
                expr = f"date_trunc('{plan.time_granularity}', {expr})"
            select_parts.append(f"{expr} AS {quote_ident(dimension)}")
            group_parts.append(expr)
        for metric in plan.metrics:
            select_parts.append(f"{self._metric_expr(metric, plan)} AS {quote_ident(self._metric_name(metric))}")
        return select_parts, group_parts

    def _where_parts(self, plan: QueryPlan) -> tuple[list[str], list[Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        for spec in plan.filters:
            clause, clause_params = self._filter_clause(spec.column, spec.operator, spec.value, plan)
            where_parts.append(clause)
            params.extend(clause_params)
        return where_parts, params

    def _metric_name(self, metric) -> str:
        return metric.name or (f"{metric.aggregation}_{metric.column}" if metric.column else "row_count")

    def _metric_expr(self, metric, plan: QueryPlan) -> str:
        if metric.aggregation == "count":
            return "count(*)"
        if metric.aggregation == "count_distinct":
            return f"count(DISTINCT {self._column_expr(metric.column, plan)})"
        if metric.aggregation == "median":
            return f"median({self._column_expr(metric.column, plan)})"
        return f"{metric.aggregation}({self._column_expr(metric.column, plan)})"

    def _having_clause(self, condition) -> str:
        left = quote_ident(condition.metric_alias)
        op_map = {
            "greater_than": ">",
            "greater_or_equal": ">=",
            "less_than": "<",
            "less_or_equal": "<=",
        }
        op = op_map[condition.operator]
        if condition.comparison == "constant":
            return f"{left} {op} {float(condition.value)}"
        if condition.comparison in {"group_average", "overall_average"}:
            return f"{left} {op} (SELECT AVG({left}) FROM base)"
        raise ValueError(f"Unsupported having comparison: {condition.comparison}")

    def _column_expr(self, column: str | None, plan: QueryPlan) -> str:
        if column is None:
            raise ValueError("column is required")
        table = self._table_for_column(column, plan)
        return f"{quote_ident(table)}.{quote_ident(column)}"

    def _table_for_column(self, column: str, plan: QueryPlan) -> str:
        for table_name in plan.tables:
            names = {item["normalized_name"] for item in self.tables[table_name]["columns"]}
            if column in names:
                return table_name
        return plan.tables[0]

    def _is_time_column(self, column: str, plan: QueryPlan) -> bool:
        table = self._table_for_column(column, plan)
        for item in self.tables[table]["columns"]:
            if item["normalized_name"] == column:
                return "datetime" in item["dtype"] or item.get("semantic_role") in {"start_time", "end_time"}
        return False

    def _filter_clause(self, column: str, operator: str, value: Any, plan: QueryPlan) -> tuple[str, list[Any]]:
        expr = self._column_expr(column, plan)
        if operator == "equals":
            return f"{expr} = ?", [value]
        if operator == "not_equals":
            return f"{expr} <> ?", [value]
        if operator == "contains":
            return f"lower(CAST({expr} AS VARCHAR)) LIKE lower(?)", [f"%{value}%"]
        if operator == "in":
            values = list(value if isinstance(value, list) else [value])
            return f"{expr} IN ({', '.join('?' for _ in values)})", values
        if operator == "greater_than":
            return f"{expr} > ?", [value]
        if operator == "greater_or_equal":
            return f"{expr} >= ?", [value]
        if operator == "less_than":
            return f"{expr} < ?", [value]
        if operator == "less_or_equal":
            return f"{expr} <= ?", [value]
        if operator in {"between", "date_between"}:
            low, high = value
            return f"{expr} BETWEEN ? AND ?", [low, high]
        if operator == "is_null":
            return f"{expr} IS NULL", []
        if operator == "is_not_null":
            return f"{expr} IS NOT NULL", []
        raise ValueError(f"Unsupported operator: {operator}")
