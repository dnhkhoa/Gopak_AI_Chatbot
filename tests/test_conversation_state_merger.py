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


def run_turn(catalog, settings, state: ConversationState, question: str):
    planned = QueryPlanner(catalog, settings).plan(question, state)
    if planned.plan.intent not in {"clarification", "refusal", "safe_failure"}:
        result = SafeQueryExecutor(catalog).execute(planned.plan)
        state.update_from_plan(planned.plan, planned.plan.output)
        state.update_from_result(result.dataframe)
    return planned


def test_change_time_followup_merges_into_previous_plan(catalog, settings):
    state = ConversationState()
    run_turn(catalog, settings, state, "Vẽ biểu đồ top 5 máy.")
    planned = run_turn(catalog, settings, state, "Chỉ lấy tháng gần nhất.")

    assert planned.plan.intent == "chart"
    assert planned.metadata["turn_type"] == "CHANGE_TIME"
    assert planned.plan.filters
    assert planned.plan.filters[0].operator == "date_between"


def test_reference_top_machine_switches_to_loss_analysis(catalog, settings):
    state = ConversationState()
    run_turn(catalog, settings, state, "Máy nào có tổng downtime cao nhất?")
    planned = run_turn(catalog, settings, state, "Với máy đứng đầu, cho tôi top 3 nguyên nhân.")

    assert planned.metadata["turn_type"] == "REFERENCE_ENTITY"
    assert planned.plan.dimensions == ["ten_ton_that"]
    assert planned.plan.filters[0].column == "may"
    assert planned.plan.filters[0].value == "Máy 11"
    assert planned.plan.limit == 3


def test_reference_missing_entity_returns_clarification(catalog, settings):
    state = ConversationState()
    planned = QueryPlanner(catalog, settings).plan("Với máy đứng đầu, cho tôi top 3 nguyên nhân.", state)

    assert planned.plan.intent in {"clarification", "safe_failure"}


def test_reset_context_clears_analytical_state(catalog, settings):
    state = ConversationState()
    run_turn(catalog, settings, state, "Top 5 nguyên nhân theo tổng downtime.")
    planned = QueryPlanner(catalog, settings).plan("Xóa toàn bộ bộ lọc.", state)

    assert planned.metadata["turn_type"] == "RESET_CONTEXT"
    assert state.active_table is None
