from __future__ import annotations

from dataclasses import replace

import pytest

from scripts_ingest import main as ingest
from src.config import get_settings
from src.conversation.state import ConversationState
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor
from src.query.schemas import FilterSpec, MetricSpec, QueryPlan
from src.query.validator import PlanValidationError, PlanValidator
from src.query_understanding.deterministic_planner import DeterministicPlanner
from src.query_understanding.entity_matcher import EntityMatcher
from src.query_understanding.time_resolver import resolve_time


@pytest.fixture(scope="module")
def catalog():
    return ingest(force=False)


@pytest.fixture()
def safe_settings():
    settings = get_settings()
    return replace(settings, enable_heuristic_fallback=False, force_legacy_fallback_mode=False)


def machine_table(catalog):
    return next(table for table in catalog["tables"] if table["table_name"].startswith("machine_downtime"))


def test_router_deterministic_route(catalog, safe_settings):
    result = QueryPlanner(catalog, safe_settings).plan("Tổng downtime là bao nhiêu?", ConversationState())
    assert result.metadata["execution_mode"] == "DETERMINISTIC"
    assert not result.metadata["llm_called"]
    assert not result.metadata["fallback_used"]


def test_router_clarification_route(catalog, safe_settings):
    result = QueryPlanner(catalog, safe_settings).plan("Máy nào tốt nhất?", ConversationState())
    assert result.metadata["execution_mode"] == "CLARIFICATION"
    assert result.plan.intent == "clarification"


def test_router_refusal_route(catalog, safe_settings):
    result = QueryPlanner(catalog, safe_settings).plan("Doanh thu năm 2024 là bao nhiêu?", ConversationState())
    assert result.metadata["execution_mode"] == "REFUSAL"
    assert result.plan.intent == "refusal"


def test_llm_failure_does_not_trigger_legacy_fallback(catalog, safe_settings):
    settings = replace(safe_settings, ollama_base_url="http://127.0.0.1:9")
    result = QueryPlanner(catalog, settings).plan("Những lỗi liên quan đến chỉnh máy.", ConversationState())
    assert result.metadata["execution_mode"] in {"SAFE_FAILURE", "DETERMINISTIC"}
    assert not result.metadata["fallback_used"]


def test_legacy_fallback_requires_force_flag(catalog, safe_settings):
    settings = replace(safe_settings, ollama_base_url="http://127.0.0.1:9", enable_heuristic_fallback=True, force_legacy_fallback_mode=True)
    result = QueryPlanner(catalog, settings).plan("Những lỗi liên quan đến chỉnh máy.", ConversationState())
    assert result.metadata["execution_mode"] in {"LEGACY_FALLBACK", "DETERMINISTIC"}


def test_deterministic_count_by_machine(catalog, safe_settings):
    parsed = DeterministicPlanner(catalog, safe_settings).parse("Đếm số lần dừng theo máy.", ConversationState())
    assert parsed.plan is not None
    assert parsed.confidence >= safe_settings.deterministic_confidence_threshold
    assert parsed.plan.dimensions == ["may"]
    assert parsed.plan.metrics[0].aggregation == "count"


def test_deterministic_topn_sum(catalog, safe_settings):
    parsed = DeterministicPlanner(catalog, safe_settings).parse("Top 5 máy theo tổng downtime.", ConversationState())
    assert parsed.plan is not None
    assert parsed.plan.limit == 5
    assert parsed.plan.sort[0].direction == "desc"


def test_time_resolver_first_latest_and_grouping(catalog):
    table = machine_table(catalog)
    first = resolve_time("Tổng downtime tháng đầu tiên trong dữ liệu.", table, "thoi_gian_bat_dau")
    latest = resolve_time("Tổng downtime tháng gần nhất trong dữ liệu.", table, "thoi_gian_bat_dau")
    monthly = resolve_time("Downtime theo tháng.", table, "thoi_gian_bat_dau")
    assert first.filters[0].value == ["2025-11-01", "2025-12-01"]
    assert latest.filters[0].value == ["2026-02-01", "2026-03-01"]
    assert monthly.granularity == "month"


def test_semantic_matcher_exact_and_no_invented_value(catalog, safe_settings):
    table = machine_table(catalog)
    matcher = EntityMatcher(catalog, safe_settings.artifacts_dir)
    exact = matcher.match_phrase("MÁY LỖI PHẦN CƠ", table, "ten_ton_that")
    none = matcher.match_phrase("VALUE_THAT_SHOULD_NOT_EXIST", table, "ten_ton_that")
    assert exact["final_selection"] == ["MÁY LỖI PHẦN CƠ"]
    assert none["final_selection"] == []


def test_invalid_plan_does_not_execute_sql(catalog):
    table = machine_table(catalog)["table_name"]
    plan = QueryPlan(tables=[table], filters=[FilterSpec(column="may", operator="greater_than", value="Máy 11")], metrics=[MetricSpec(aggregation="count", name="row_count")])
    with pytest.raises(PlanValidationError):
        PlanValidator(catalog).validate(plan)


def test_out_of_domain_does_not_execute_sql(catalog, safe_settings):
    result = QueryPlanner(catalog, safe_settings).plan("Dự báo giá cổ phiếu ngày mai.", ConversationState())
    assert result.plan.intent == "refusal"
    with pytest.raises(Exception):
        SafeQueryExecutor(catalog).execute(result.plan)
