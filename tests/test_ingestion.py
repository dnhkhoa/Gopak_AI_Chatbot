from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts_ingest import main as ingest
from src.config import get_settings
from src.ingestion.cache_manager import ParquetCache
from src.ingestion.header_detector import detect_header
from src.ingestion.normalizer import normalize_column_name, parse_datetime_series, parse_duration_seconds
from src.ingestion.workbook_scanner import find_excel_files


def test_header_detection_after_metadata():
    rows = [["Report"], [None], ["No.", "Máy", "Thời lượng"], [1, "Máy 1", "00:01:00"]]
    detected = detect_header(rows)
    assert detected is not None
    assert detected.header_row_index == 2


def test_column_normalization_vietnamese():
    assert normalize_column_name("Mã đăng ký") == "ma_dang_ky"
    assert normalize_column_name("Thời gian bắt đầu") == "thoi_gian_bat_dau"


def test_duration_parsing():
    assert parse_duration_seconds("00:01:30") == 90
    assert parse_duration_seconds("1 02:00:00") == 93600


def test_date_parsing():
    series = parse_datetime_series(pd.Series(["2026-02-03 10:00:00", "bad"]))
    assert series.notna().sum() == 1


def test_parquet_cache_real_files():
    settings = get_settings()
    files = find_excel_files(settings.root)
    assert len(files) == 3
    tables = ParquetCache(settings.cache_dir).refresh(files, force=False)
    assert len(tables) >= 3
    assert all(Path(table["parquet_path"]).exists() for table in tables)
    assert {"Cup3.xlsx", "Loss_Assignment_20260203_100840.xlsx", "Machine_Downtime_20260203_100753.xlsx"}.issubset(
        {Path(str(table.get("source_file") or table.get("source_path") or "")).name for table in tables}
    )


def test_build_catalog_real_files():
    catalog = ingest(force=False)
    assert len(catalog["tables"]) >= 3
    assert any(table["row_count"] > 9000 for table in catalog["tables"])
