from __future__ import annotations

from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz


def _sample_values(series: pd.Series, limit: int = 5000) -> set[str]:
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    return set(values.head(limit).tolist())


def _join_candidate_column(column: str, series: pd.Series) -> bool:
    blocked = {"no", "stt", "index", "_source_row"}
    if column in blocked or column.startswith("_") or column.endswith("_seconds"):
        return False
    if "thoi_luong" in column or "duration" in column:
        return False
    if pd.api.types.is_numeric_dtype(series):
        return False
    return True


def detect_relationships(tables: dict[str, pd.DataFrame], profiles: dict[str, dict]) -> list[dict]:
    relationships: list[dict] = []
    for left_name, right_name in combinations(tables.keys(), 2):
        left_df, right_df = tables[left_name], tables[right_name]
        for left_col in left_df.columns:
            if not _join_candidate_column(left_col, left_df[left_col]):
                continue
            for right_col in right_df.columns:
                if not _join_candidate_column(right_col, right_df[right_col]):
                    continue
                left_values = _sample_values(left_df[left_col])
                right_values = _sample_values(right_df[right_col])
                if not left_values or not right_values:
                    continue
                overlap = len(left_values & right_values)
                if overlap == 0:
                    continue
                overlap_ratio = overlap / min(len(left_values), len(right_values))
                name_score = fuzz.token_sort_ratio(left_col, right_col) / 100
                confidence = round((overlap_ratio * 0.75) + (name_score * 0.25), 3)
                if confidence >= 0.55 and overlap >= 3:
                    relationships.append(
                        {
                            "left_table": left_name,
                            "left_column": left_col,
                            "right_table": right_name,
                            "right_column": right_col,
                            "overlap_count": overlap,
                            "overlap_ratio": round(overlap_ratio, 3),
                            "name_similarity": round(name_score, 3),
                            "confidence": confidence,
                            "evidence": "compatible sampled values and similar column names",
                        }
                    )
    return sorted(relationships, key=lambda item: item["confidence"], reverse=True)
