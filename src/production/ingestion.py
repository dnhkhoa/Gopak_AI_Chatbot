from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings
from src.sources.registry import ProductionSource, SourceRegistry


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _column_profile(df: pd.DataFrame, column: str, role: str | None = None) -> dict[str, Any]:
    series = df[column]
    profile = {
        "original_name": column,
        "normalized_name": column,
        "dtype": str(series.dtype),
        "semantic_role": role,
        "null_ratio": round(float(series.isna().mean()), 4) if len(series) else 1.0,
        "cardinality": int(series.nunique(dropna=True)),
        "sample_values": [str(value)[:80] for value in series.dropna().astype(str).drop_duplicates().head(5).tolist()],
    }
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        non_null = series.dropna()
        profile["min"] = non_null.min() if not non_null.empty else None
        profile["max"] = non_null.max() if not non_null.empty else None
    return profile


def _metrics_for_source(source: ProductionSource, df: pd.DataFrame) -> list[dict[str, Any]]:
    metrics = [{"name": "row_count", "aggregation": "count", "column": None}]
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            metrics.append({"name": f"sum_{column}", "aggregation": "sum", "column": column})
            metrics.append({"name": f"avg_{column}", "aggregation": "avg", "column": column})
    return metrics


def _load_source_dataframe(source: ProductionSource) -> tuple[pd.DataFrame, dict[str, str]]:
    if source.source_id == "apqoee_cumulative":
        df = pd.read_excel(source.workbook_path, sheet_name=0)
        df["ExecuteAt"] = pd.to_datetime(df["ExecuteAt"], utc=True, errors="coerce")
        roles = {"ExecuteAt": "timestamp"}
        return df, roles

    df = pd.read_excel(source.workbook_path, sheet_name=0, header=34)
    mapping = {
        "No.": "record_no",
        "Máy": "machine",
        "Thời gian bắt đầu": "start_time",
        "Thời gian kết thúc": "end_time",
        "Thời lượng": "duration_text",
        "Tên tổn thất": "loss_name",
        "Nhóm tổn thất": "loss_group",
        "Loại tổn thất": "loss_type",
        "Note": "note",
    }
    df = df.rename(columns={key: value for key, value in mapping.items() if key in df.columns})
    keep = [column for column in mapping.values() if column in df.columns]
    df = df[keep].copy()
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
    if "machine" in df.columns:
        df["may"] = df["machine"]
    if "start_time" in df.columns:
        df["thoi_gian_bat_dau"] = df["start_time"]
    if "end_time" in df.columns:
        df["thoi_gian_ket_thuc"] = df["end_time"]
    if "duration_text" in df.columns:
        df["thoi_luong"] = df["duration_text"]
        parts = df["duration_text"].astype(str).str.extract(r"(?P<h>\d+):(?P<m>\d+):(?P<s>\d+)")
        seconds = (
            pd.to_numeric(parts["h"], errors="coerce").fillna(0) * 3600
            + pd.to_numeric(parts["m"], errors="coerce").fillna(0) * 60
            + pd.to_numeric(parts["s"], errors="coerce").fillna(0)
        )
        df["thoi_luong_seconds"] = seconds
    if "loss_name" in df.columns:
        df["ten_ton_that"] = df["loss_name"]
    if "loss_group" in df.columns:
        df["nhom_ton_that"] = df["loss_group"]
    if "loss_type" in df.columns:
        df["loai_ton_that"] = df["loss_type"]
    df["_source_id"] = source.source_id
    df["_source_file"] = source.workbook_path.name
    preferred = [
        "record_no",
        "may",
        "thoi_gian_bat_dau",
        "thoi_gian_ket_thuc",
        "thoi_luong",
        "thoi_luong_seconds",
        "ten_ton_that",
        "nhom_ton_that",
        "loai_ton_that",
        "machine",
        "start_time",
        "end_time",
        "duration_text",
        "loss_name",
        "loss_group",
        "loss_type",
        "note",
        "_source_id",
        "_source_file",
    ]
    df = df[[column for column in preferred if column in df.columns]]
    roles = {
        "machine": "machine",
        "may": "machine",
        "start_time": "start_time",
        "thoi_gian_bat_dau": "start_time",
        "end_time": "end_time",
        "thoi_gian_ket_thuc": "end_time",
        "duration_text": "duration",
        "thoi_luong": "duration",
        "thoi_luong_seconds": "duration_seconds",
        "loss_name": "loss_name",
        "ten_ton_that": "loss_name",
        "loss_group": "loss_group",
        "nhom_ton_that": "loss_group",
        "loss_type": "loss_type",
        "loai_ton_that": "loss_type",
        "_source_id": "provenance",
        "_source_file": "provenance",
    }
    return df, roles


def refresh_production_bundle(settings: Settings, force: bool = False) -> dict[str, Any]:
    registry = SourceRegistry(settings)
    sources = registry.load()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = settings.cache_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    table_entries: list[dict[str, Any]] = []
    catalog_tables: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    active_table_paths: set[Path] = set()
    for source in sources:
        if source.status != "ready":
            continue
        df, roles = _load_source_dataframe(source)
        table_name = f"{source.source_id}_main"
        parquet_path = tables_dir / f"{table_name}_{(source.checksum or 'missing')[:12]}.parquet"
        df.to_parquet(parquet_path, index=False)
        active_table_paths.add(parquet_path.resolve())
        profile = {
            "source_file": source.workbook_path.name,
            "source_sheet": "ListChartData" if source.source_id == "apqoee_cumulative" else "Report",
            "table_name": table_name,
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "column_mapping": {column: column for column in df.columns},
            "semantic_roles": {column: role for column, role in roles.items() if column in df.columns},
            "validation": {
                "source_id": source.source_id,
                "checksum": source.checksum,
                "schema_fingerprint": source.schema_fingerprint,
            },
        }
        entry = {
            "table_name": table_name,
            "source_path": str(source.workbook_path),
            "source_file": source.workbook_path.name,
            "source_sheet": profile["source_sheet"],
            "file_id": source.source_id,
            "source_file_id": source.source_id,
            "source_id": source.source_id,
            "sha256": source.checksum,
            "schema_fingerprint": source.schema_fingerprint,
            "parquet_path": str(parquet_path),
            "profile": profile,
        }
        table_entries.append(entry)
        catalog_tables.append(
            {
                "table_name": table_name,
                "source": f"{source.display_name} / {profile['source_sheet']}",
                "source_path": str(source.workbook_path),
                "source_file": source.workbook_path.name,
                "source_sheet": profile["source_sheet"],
                "source_id": source.source_id,
                "parquet_path": str(parquet_path),
                "file_id": source.source_id,
                "source_file_id": source.source_id,
                "sha256": source.checksum,
                "schema_fingerprint": source.schema_fingerprint,
                "row_count": int(len(df)),
                "columns": [_column_profile(df, column, roles.get(column)) for column in df.columns],
                "metrics": _metrics_for_source(source, df),
                "profile": profile,
            }
        )

    for path in tables_dir.glob("*.parquet"):
        if path.resolve() not in active_table_paths:
            path.unlink()

    manifest = {
        "schema": "production_bundle_manifest_v1",
        "updated_at": now,
        "files": {
            str(source.workbook_path): {
                "source_id": source.source_id,
                "sha256": source.checksum,
                "schema_fingerprint": source.schema_fingerprint,
                "tables": [entry for entry in table_entries if entry["source_id"] == source.source_id],
            }
            for source in sources
            if source.status == "ready"
        },
        "tables": table_entries,
        "previous_manifest_retained": False,
    }
    catalog = {
        "schema": "production_bundle_catalog_v1",
        "updated_at": now,
        "tables": catalog_tables,
        "relationships": [],
        "source_registry": [source.public_dict() for source in sources],
    }
    _json_write(settings.cache_dir / "manifest.json", manifest)
    _json_write(settings.cache_dir / "data_catalog.json", catalog)
    return catalog
