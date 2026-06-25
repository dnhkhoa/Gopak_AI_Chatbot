from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.application.overview_analysis import build_domain_aware_overview, classify_columns


def _catalog(tmp_path: Path, df: pd.DataFrame, *, source_file: str = "workbook.xlsx", roles: dict[str, str] | None = None) -> dict:
    path = tmp_path / f"{source_file}.parquet"
    df.to_parquet(path)
    roles = roles or {}
    table = {
        "table_name": source_file.replace(".xlsx", "").lower(),
        "source": f"{source_file} / Sheet1",
        "source_file": source_file,
        "source_sheet": "Sheet1",
        "parquet_path": str(path),
        "row_count": len(df),
        "columns": [
            {
                "normalized_name": col,
                "original_name": col,
                "dtype": str(df[col].dtype),
                "semantic_role": roles.get(col),
                "sample_values": [str(x) for x in df[col].dropna().head(3).tolist()],
            }
            for col in df.columns
        ],
    }
    return {"tables": [table], "relationships": []}


def _selected_text(brief) -> str:
    return " ".join(item.statement + " " + item.primary_metric for item in brief.selected_insights).lower()


def test_row_index_excluded_from_overview_insights(tmp_path: Path) -> None:
    df = pd.DataFrame({"No.": range(1, 101), "Machine": ["A", "B"] * 50, "Duration": [10, 20] * 50, "Cause": ["Jam", "Setup"] * 50})
    catalog = _catalog(tmp_path, df, roles={"Machine": "machine", "Duration": "duration_seconds", "Cause": "loss_name"})
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    role = next(item for item in brief.column_profiles if item.column_name == "No.")
    assert role.semantic_role == "ROW_INDEX"
    assert "no." not in _selected_text(brief)


def test_unique_identifier_excluded_from_overview_insights(tmp_path: Path) -> None:
    df = pd.DataFrame({"event_id": [f"id-{i:04d}" for i in range(100)], "Machine": ["A", "B"] * 50, "duration_seconds": [10, 20] * 50})
    catalog = _catalog(tmp_path, df, roles={"Machine": "machine", "duration_seconds": "duration_seconds"})
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    role = next(item for item in brief.column_profiles if item.column_name == "event_id")
    assert role.semantic_role == "IDENTIFIER"
    assert "event_id" not in _selected_text(brief)


def test_constant_column_is_not_promoted_as_insight(tmp_path: Path) -> None:
    df = pd.DataFrame({"constant": ["same"] * 100, "category": ["A", "B"] * 50, "amount": [1, 5] * 50})
    catalog = _catalog(tmp_path, df)
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    assert "constant" not in _selected_text(brief)


def test_downtime_overview_uses_business_metrics(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "No": range(1, 7),
            "machine": ["M1", "M1", "M2", "M2", "M2", "M3"],
            "duration_seconds": [100, 200, 400, 500, 600, 50],
            "cause": ["A", "B", "A", "A", "C", "C"],
            "start_time": pd.date_range("2026-01-01", periods=6),
        }
    )
    catalog = _catalog(tmp_path, df, source_file="machine_events.xlsx", roles={"machine": "machine", "duration_seconds": "duration_seconds", "cause": "loss_name", "start_time": "start_time", "No": "record_no"})
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    text = _selected_text(brief)
    assert brief.capability_profile.selected_domain == "machine_downtime"
    assert "machine" in text or "may" in text
    assert "downtime" in text
    assert "no" not in text


def test_loss_overview_focuses_distribution(tmp_path: Path) -> None:
    df = pd.DataFrame({"STT": range(1, 7), "loss_group": ["Prod", "Prod", "Maint", "Prod", "QC", "Prod"], "loss_reason": ["A", "B", "A", "A", "C", "B"], "duration_seconds": [10, 20, 30, 40, 50, 60]})
    catalog = _catalog(tmp_path, df, source_file="loss_register.xlsx", roles={"loss_group": "loss_group", "loss_reason": "loss_name", "duration_seconds": "duration_seconds", "STT": "record_no"})
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    assert brief.capability_profile.selected_domain == "loss_assignment"
    assert any(item.insight_type in {"distribution", "concentration"} for item in brief.selected_insights)


def test_entry_transaction_overview_uses_value_and_category(tmp_path: Path) -> None:
    df = pd.DataFrame({"row": range(1, 7), "gate": ["G1", "G1", "G2", "G1", "G3", "G2"], "gia_tri_can": [10, 20, 30, 40, 50, 60], "transaction_date": pd.date_range("2026-01-01", periods=6)})
    catalog = _catalog(tmp_path, df, source_file="entry_transaction.xlsx", roles={"row": "record_no"})
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    assert brief.capability_profile.selected_domain == "entry_transaction"
    text = _selected_text(brief)
    assert "gia_tri_can" in text or "transaction" in text or "giao" in text
    assert "row" not in text


def test_generic_workbook_uses_business_dimension_and_measure(tmp_path: Path) -> None:
    df = pd.DataFrame({"uuid": [f"u{i}" for i in range(20)], "region": ["North", "South"] * 10, "sales": [10, 20] * 10})
    catalog = _catalog(tmp_path, df)
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    text = _selected_text(brief)
    assert "region" in text or "sales" in text
    assert "uuid" not in text


def test_insufficient_useful_columns_does_not_fabricate_insights(tmp_path: Path) -> None:
    df = pd.DataFrame({"id": [f"id-{i}" for i in range(20)], "empty_text": [None] * 20})
    catalog = _catalog(tmp_path, df)
    brief = build_domain_aware_overview(catalog)
    assert brief is not None
    assert len(brief.selected_insights) <= 1
    assert "insufficient_business_columns" in brief.quality_warnings
