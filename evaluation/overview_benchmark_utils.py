from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def catalog_for_frame(tmp_path: Path, df: pd.DataFrame, *, source_file: str, roles: dict[str, str] | None = None) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
                "sample_values": [str(x) for x in df[col].dropna().head(5).tolist()],
            }
            for col in df.columns
        ],
    }
    return {"tables": [table], "relationships": []}


def benchmark_cases(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        {
            "id": "row_index_downtime",
            "domain": "machine_downtime",
            "catalog": catalog_for_frame(
                tmp_path,
                pd.DataFrame(
                    {
                        "No.": range(1, 101),
                        "machine": ["M1", "M2", "M3", "M2"] * 25,
                        "duration_seconds": [100, 400, 50, 200] * 25,
                        "cause": ["Jam", "Setup", "QC", "Jam"] * 25,
                        "start_time": pd.date_range("2026-01-01", periods=100, freq="h"),
                    }
                ),
                source_file="machine_events.xlsx",
                roles={"No.": "record_no", "machine": "machine", "duration_seconds": "duration_seconds", "cause": "loss_name", "start_time": "start_time"},
            ),
            "forbidden": ["No.", "no"],
            "required_terms": ["machine", "downtime"],
        },
        {
            "id": "unique_id_generic",
            "domain": "generic_tabular",
            "catalog": catalog_for_frame(
                tmp_path,
                pd.DataFrame({"event_id": [f"id-{i:04d}" for i in range(80)], "region": ["North", "South"] * 40, "sales": [10, 30] * 40}),
                source_file="sales_register.xlsx",
            ),
            "forbidden": ["event_id"],
            "required_terms": ["region", "sales"],
        },
        {
            "id": "constant_column",
            "domain": "generic_tabular",
            "catalog": catalog_for_frame(
                tmp_path,
                pd.DataFrame({"constant": ["same"] * 80, "category": ["A", "B"] * 40, "amount": [5, 9] * 40}),
                source_file="generic_business.xlsx",
            ),
            "forbidden": ["constant"],
            "required_terms": ["category", "amount"],
        },
        {
            "id": "loss_assignment",
            "domain": "loss_assignment",
            "catalog": catalog_for_frame(
                tmp_path,
                pd.DataFrame({"STT": range(1, 81), "loss_group": ["Prod", "Maint", "QC", "Prod"] * 20, "loss_reason": ["A", "B", "C", "A"] * 20, "duration_seconds": [10, 20, 40, 30] * 20}),
                source_file="loss_assignment.xlsx",
                roles={"STT": "record_no", "loss_group": "loss_group", "loss_reason": "loss_name", "duration_seconds": "duration_seconds"},
            ),
            "forbidden": ["STT", "stt"],
            "required_terms": ["loss", "ton", "nhom"],
        },
        {
            "id": "entry_transaction",
            "domain": "entry_transaction",
            "catalog": catalog_for_frame(
                tmp_path,
                pd.DataFrame({"row": range(1, 81), "gate": ["G1", "G2", "G1", "G3"] * 20, "gia_tri_can": [10, 20, 30, 40] * 20, "transaction_date": pd.date_range("2026-01-01", periods=80, freq="h")}),
                source_file="entry_transaction.xlsx",
                roles={"row": "record_no"},
            ),
            "forbidden": ["row"],
            "required_terms": ["giao", "transaction", "gia_tri_can", "gate"],
        },
        {
            "id": "insufficient",
            "domain": "generic_tabular",
            "catalog": catalog_for_frame(
                tmp_path,
                pd.DataFrame({"id": [f"id-{i}" for i in range(30)], "empty_text": [None] * 30}),
                source_file="ids_only.xlsx",
            ),
            "forbidden": ["id"],
            "required_terms": [],
            "insufficient": True,
        },
    ]


def insight_text(brief: Any) -> str:
    parts: list[str] = [
        str(getattr(getattr(brief, "capability_profile", None), "selected_domain", "")),
        " ".join(str(item) for item in getattr(brief, "business_dimensions", []) or []),
        " ".join(str(item) for item in getattr(brief, "business_measures", []) or []),
    ]
    for item in getattr(brief, "selected_insights", []) or []:
        parts.extend(
            [
                str(getattr(item, "title", "")),
                str(getattr(item, "statement", "")),
                str(getattr(item, "primary_metric", "")),
                str(getattr(item, "primary_entity", "")),
            ]
        )
        for evidence in getattr(item, "evidence", []) or []:
            parts.extend(str(evidence.get(key, "")) for key in ["dimension", "column", "metric", "entity"])
    return " ".join(part for part in parts if part).lower()
