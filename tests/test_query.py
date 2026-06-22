from __future__ import annotations

import pandas as pd
import pytest

from scripts_ingest import main as ingest
from src.conversation.state import ConversationState
from src.llm.planner import QueryPlanner
from src.config import get_settings
from src.query.executor import SafeQueryExecutor
from src.query.schemas import FilterSpec, MetricSpec, QueryPlan
from src.query.sql_builder import SQLBuilder
from src.query.validator import PlanValidationError, PlanValidator
from src.rendering.chart_renderer import chart_spec_valid


@pytest.fixture(scope="module")
def catalog():
    return ingest(force=False)


def machine_table(catalog):
    return next(table for table in catalog["tables"] if table["table_name"].startswith("machine_downtime"))["table_name"]


def test_pydantic_plan_validation():
    plan = QueryPlan(tables=["t"], metrics=[MetricSpec(aggregation="count", name="row_count")])
    assert plan.limit == 20


def test_invalid_column_rejected(catalog):
    table = machine_table(catalog)
    plan = QueryPlan(tables=[table], dimensions=["not_a_column"], metrics=[MetricSpec(aggregation="count", name="row_count")])
    with pytest.raises(PlanValidationError):
        PlanValidator(catalog).validate(plan)


def test_invalid_operator_rejected():
    with pytest.raises(Exception):
        FilterSpec(column="may", operator="drop_table", value="x")  # type: ignore[arg-type]


def test_safe_sql_generation(catalog):
    table = machine_table(catalog)
    plan = QueryPlan(tables=[table], dimensions=["may"], metrics=[MetricSpec(aggregation="sum", column="thoi_luong_seconds", name="total_duration_seconds")], limit=5)
    PlanValidator(catalog).validate(plan)
    sql, params = SQLBuilder(catalog).build(plan)
    assert "read_parquet(?)" in sql
    assert "DROP" not in sql.upper()
    assert params


def test_duckdb_query(catalog):
    table = machine_table(catalog)
    plan = QueryPlan(tables=[table], dimensions=["may"], metrics=[MetricSpec(aggregation="sum", column="thoi_luong_seconds", name="total_duration_seconds")], limit=5)
    result = SafeQueryExecutor(catalog).execute(plan)
    assert not result.dataframe.empty


def test_conversation_state(catalog):
    table = machine_table(catalog)
    state = ConversationState()
    plan = QueryPlan(tables=[table], metrics=[MetricSpec(aggregation="count", name="row_count")])
    state.update_from_plan(plan, "table")
    assert state.active_tables == [table]
    state.reset()
    assert state.active_tables == []


def test_empty_result_handling(catalog):
    table = machine_table(catalog)
    plan = QueryPlan(tables=[table], filters=[FilterSpec(column="may", operator="equals", value="NO_SUCH_MACHINE")], metrics=[MetricSpec(aggregation="count", name="row_count")])
    result = SafeQueryExecutor(catalog).execute(plan)
    assert len(result.dataframe) == 1


def test_chart_spec_validation(catalog):
    table = machine_table(catalog)
    plan = QueryPlan(intent="chart", tables=[table], dimensions=["may"], metrics=[MetricSpec(aggregation="sum", column="thoi_luong_seconds", name="total_duration_seconds")], output="bar")
    assert chart_spec_valid(pd.DataFrame({"may": ["A"], "total_duration_seconds": [1]}), plan)


def test_planner_heuristic(catalog):
    planner = QueryPlanner(catalog, get_settings())
    planned = planner.plan("Máy nào có thời gian downtime cao nhất?", ConversationState())
    assert planned.plan.tables
    assert planned.plan.metrics

