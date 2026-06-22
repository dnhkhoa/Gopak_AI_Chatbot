from __future__ import annotations

from dataclasses import replace

import pytest

from scripts_ingest import main as ingest
from src.config import get_settings
from src.conversation.state import ConversationState
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor


@pytest.fixture(scope="module")
def catalog():
    return ingest(force=False)


@pytest.fixture(scope="module")
def settings():
    return replace(get_settings(), enable_heuristic_fallback=False, force_legacy_fallback_mode=False)


def plan_question(catalog, settings, question: str, state: ConversationState | None = None):
    return QueryPlanner(catalog, settings).plan(question, state or ConversationState()).plan


def test_multiple_metrics_plan_and_result(catalog, settings):
    plan = plan_question(
        catalog,
        settings,
        "Hãy tìm top 5 máy có tổng downtime cao nhất, hiển thị thêm số lần dừng và thời lượng trung bình.",
    )
    result = SafeQueryExecutor(catalog).execute(plan)

    assert plan.query_complexity == "complex"
    assert [metric.name for metric in plan.metrics] == ["total_duration_seconds", "row_count", "avg_duration_seconds"]
    assert plan.limit == 5
    assert {"may", "total_duration_seconds", "row_count", "avg_duration_seconds"}.issubset(result.dataframe.columns)


def test_percentage_of_total_query(catalog, settings):
    plan = plan_question(catalog, settings, "Xếp hạng nguyên nhân theo tỷ lệ phần trăm số lần dừng.")
    result = SafeQueryExecutor(catalog).execute(plan)

    assert plan.metrics[0].percentage_of_total is True
    assert "percentage" in result.dataframe.columns
    assert 99.9 <= float(result.dataframe["percentage"].sum()) <= 100.1


def test_above_average_group_filter(catalog, settings):
    plan = plan_question(catalog, settings, "Các máy có tổng downtime cao hơn mức trung bình theo máy.")
    result = SafeQueryExecutor(catalog).execute(plan)

    assert plan.having[0].comparison == "group_average"
    assert len(result.dataframe) == 4
    assert result.dataframe.iloc[0]["may"] == "Máy 11"


def test_windowed_month_machine_ranking(catalog, settings):
    plan = plan_question(catalog, settings, "Top máy theo từng tháng.")
    result = SafeQueryExecutor(catalog).execute(plan)

    assert plan.ranking is not None
    assert plan.ranking.partition_by == ["thoi_gian_bat_dau"]
    assert "_rank" in result.dataframe.columns
    assert result.dataframe.iloc[0]["thoi_gian_bat_dau"].isoformat().startswith("2025-11")
