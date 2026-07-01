from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.catalog.relationship_detector import detect_relationships


def _json_safe(value: Any) -> Any:
    if pd.isna(value) if not isinstance(value, (list, dict, tuple, set)) else False:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _column_profile(series: pd.Series, original_name: str | None, semantic_role: str | None) -> dict:
    non_null = series.dropna()
    samples = []
    for value in non_null.astype(str).drop_duplicates().head(8).tolist():
        if len(value) <= 80:
            samples.append(value)
    profile = {
        "original_name": original_name,
        "normalized_name": series.name,
        "dtype": str(series.dtype),
        "semantic_role": semantic_role,
        "null_ratio": round(float(series.isna().mean()), 4) if len(series) else 1.0,
        "cardinality": int(non_null.nunique(dropna=True)),
        "sample_values": samples,
        "description": _describe_column(series.name, original_name, semantic_role),
    }
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        if non_null.empty:
            profile["min"] = profile["max"] = None
        else:
            profile["min"] = _json_safe(non_null.min())
            profile["max"] = _json_safe(non_null.max())
    return profile


def _describe_column(name: str, original_name: str | None, semantic_role: str | None) -> str:
    if semantic_role == "machine":
        return "Machine or production line identifier."
    if semantic_role == "duration":
        return "Original duration value from Excel."
    if semantic_role == "duration_seconds":
        return "Duration normalized to seconds for aggregation."
    if semantic_role in {"start_time", "end_time"}:
        return "Datetime column parsed from Excel."
    if semantic_role == "loss_name":
        return "Downtime/loss reason or event name."
    if semantic_role == "loss_group":
        return "Loss category/group."
    return f"Column from source header {original_name or name}."


def build_catalog(table_entries: list[dict], cache_dir: Path) -> dict:
    tables: dict[str, pd.DataFrame] = {}
    profiles_by_table: dict[str, dict] = {}
    catalog_tables = []
    for entry in table_entries:
        df = pd.read_parquet(entry["parquet_path"])
        table_name = entry["table_name"]
        profile = entry["profile"]
        tables[table_name] = df
        profiles_by_table[table_name] = profile
        reverse_mapping = {normalized: original for original, normalized in profile.get("column_mapping", {}).items()}
        semantic_roles = profile.get("semantic_roles", {})
        column_profiles = [
            _column_profile(df[column], reverse_mapping.get(column), semantic_roles.get(column))
            for column in df.columns
        ]
        metrics = []
        for col in column_profiles:
            if col.get("semantic_role") in {"duration_seconds"}:
                metrics.extend([{"name": f"sum_{col['normalized_name']}", "aggregation": "sum", "column": col["normalized_name"]}])
            if col["dtype"].startswith(("int", "float")):
                metrics.append({"name": f"avg_{col['normalized_name']}", "aggregation": "avg", "column": col["normalized_name"]})
        metrics.append({"name": "row_count", "aggregation": "count", "column": None})
        catalog_tables.append(
            {
                "table_name": table_name,
                "source": f"{entry['source_file']} / {entry['source_sheet']}",
                "source_path": entry["source_path"],
                "source_file": entry.get("source_file"),
                "source_sheet": entry.get("source_sheet"),
                "parquet_path": entry["parquet_path"],
                "file_id": entry.get("file_id") or entry.get("source_file_id"),
                "source_file_id": entry.get("source_file_id") or entry.get("file_id"),
                "source_id": entry.get("source_id"),
                "sha256": entry.get("sha256"),
                "row_count": len(df),
                "columns": column_profiles,
                "metrics": metrics,
                "profile": profile,
            }
        )
    relationships = detect_relationships(tables, profiles_by_table)
    catalog = {"tables": catalog_tables, "relationships": relationships}
    output = cache_dir / "data_catalog.json"
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return catalog


def load_catalog(cache_dir: Path) -> dict:
    return json.loads((cache_dir / "data_catalog.json").read_text(encoding="utf-8"))
