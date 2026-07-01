from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.config import Settings
from src.production.ingestion import refresh_production_bundle
from src.production.service import ProductionAnalyticsService
from src.query.schemas import QueryPlan
from src.query.validator import PlanValidationError, PlanValidator
from src.sources.registry import ProductionSource, SourceRegistry
from src.sources.routing import SourceRouter


def _settings(tmp_path: Path | None = None, timezone: str = "Asia/Ho_Chi_Minh") -> Settings:
    root = Path(__file__).resolve().parents[1]
    return Settings(
        root=root,
        cache_dir=(tmp_path or root / "cache"),
        reports_dir=root / "reports",
        artifacts_dir=root / "artifacts",
        memory_db_path=root / "data" / "test_memory.db",
        business_timezone=timezone,
        customer_production_mode=True,
    )


def test_source_registry_uses_exact_production_sources() -> None:
    sources = SourceRegistry(_settings()).load()
    assert {source.source_id for source in sources} == {"machine_downtime", "loss_assignment", "apqoee_cumulative"}
    assert all("Entry" + "Transaction" not in source.workbook_path.name for source in sources)
    assert next(source for source in sources if source.source_id == "apqoee_cumulative").workbook_path.name == "Cup3.xlsx"


def test_source_router_single_two_three_source_cases() -> None:
    sources = SourceRegistry(_settings()).load()
    router = SourceRouter(sources)

    single = router.route("OEE tich luy den ngay 10/11/2025 la bao nhieu?")
    assert single.source_ids == ("apqoee_cumulative",)
    assert single.execution_strategy == "single_source"

    two = router.route("Den ngay 10/11/2025, OEE thay doi the nao trong cac ngay downtime cao?")
    assert two.source_ids == ("apqoee_cumulative", "machine_downtime")
    assert two.execution_strategy == "parallel_queries_then_merge"

    three = router.route("Phan tich OEE, downtime va nhom ton that tu dau thang den ngay 10/11/2025")
    assert three.source_ids == ("apqoee_cumulative", "machine_downtime", "loss_assignment")
    assert three.execution_strategy == "parallel_queries_then_merge"


def test_apqoee_as_of_uses_latest_snapshot_at_or_before_requested_day() -> None:
    settings = _settings()
    response = ProductionAnalyticsService(settings).process("test", "OEE tich luy den ngay 10/11/2025 la bao nhieu?")

    df = pd.read_excel(settings.root / "Cup3.xlsx", sheet_name=0)
    execute_local = pd.to_datetime(df["ExecuteAt"], utc=True).dt.tz_convert(settings.business_timezone)
    expected = df.assign(_execute_local=execute_local).query("_execute_local <= '2025-11-11 00:00:00+07:00'").sort_values("_execute_local").iloc[-1]

    assert response.response_type == "table"
    assert response.metadata["sources_used"] == ["apqoee_cumulative"]
    assert response.table is not None
    first = response.table.rows[0]
    assert first["metric"] == "Cumulative OEE"
    assert first["value"] == round(float(expected["OEE"]) * 100, 2)
    assert "cumulative" in response.summary.lower()


def test_period_specific_oee_is_rejected_without_performance_formula() -> None:
    response = ProductionAnalyticsService(_settings()).process("test", "OEE rieng ngay 10/11/2025 la bao nhieu?")
    assert response.response_type == "refusal"
    assert response.metadata["status"] == "PLAN_REJECTED"
    assert response.metadata["fallback_used"] is False


def test_business_timezone_required_for_day_questions() -> None:
    response = ProductionAnalyticsService(_settings(timezone="")).process("test", "Downtime ngay 10/11/2025 la bao nhieu?")
    assert response.response_type == "error"
    assert response.metadata["status"] == "SAFE_FAILURE"


def test_interval_overlap_clips_events(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    service = ProductionAnalyticsService(settings)
    source = ProductionSource(
        source_id="machine_downtime",
        display_name="Machine Downtime",
        workbook_path=settings.root / "Machine_Downtime_20260203_100753.xlsx",
        business_domain="machine_downtime",
        schema_version="test",
        checksum="test",
        schema_fingerprint="test",
        primary_grain="downtime_event",
        timestamp_column="start_time",
        timestamp_storage_timezone="local_workbook_time",
        business_timezone=settings.business_timezone,
        supported_metrics=("downtime_duration",),
        entity_keys=("machine",),
        status="ready",
    )
    monkeypatch.setattr(
        service,
        "_load_event_workbook",
        lambda _path: pd.DataFrame(
            {
                "machine": ["A", "A", "B"],
                "start_time": pd.to_datetime(["2025-11-09 23:00:00", "2025-11-10 23:30:00", "2025-11-11 00:00:00"]),
                "end_time": pd.to_datetime(["2025-11-10 01:00:00", "2025-11-11 01:00:00", "2025-11-11 02:00:00"]),
            }
        ),
    )
    plan = service._plan_for_source("Downtime ngay 10/11/2025", SourceRouter([source]).route("Downtime ngay 10/11/2025"), source)
    rows, _notes = service._execute_events(source, plan)
    duration = next(row for row in rows if row["metric"] == "Downtime duration")
    assert duration["value"] == 1.5


def test_multi_table_plan_without_join_is_rejected() -> None:
    catalog = {
        "tables": [
            {"table_name": "a", "columns": [{"normalized_name": "id", "dtype": "int64"}]},
            {"table_name": "b", "columns": [{"normalized_name": "id", "dtype": "int64"}]},
        ],
        "relationships": [],
    }
    plan = QueryPlan(tables=["a", "b"])
    with pytest.raises(PlanValidationError):
        PlanValidator(catalog).validate(plan)


def test_production_ingest_prunes_deprecated_entry_source_from_active_catalog(tmp_path: Path) -> None:
    settings = _settings(tmp_path=tmp_path)
    catalog = refresh_production_bundle(settings, force=True)
    text = (settings.cache_dir / "data_catalog.json").read_text(encoding="utf-8") if (settings.cache_dir / "data_catalog.json").exists() else ""
    assert len(catalog["tables"]) == 3
    assert "Entry" + "Transaction" not in text
