from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
from rapidfuzz import fuzz, process

from src.query_understanding.catalog_utils import column_info
from src.query_understanding.text import normalize_text


class EntityMatcher:
    def __init__(self, catalog: dict, artifacts_dir: Path | str = "artifacts"):
        self.catalog = catalog
        self.artifacts_dir = Path(artifacts_dir)
        self._cache: dict[tuple[str, str], list[str]] = {}

    def unique_values(self, table: dict, column: str) -> list[str]:
        key = (table["table_name"], column)
        if key in self._cache:
            return self._cache[key]
        with duckdb.connect(database=":memory:") as con:
            rows = con.execute(
                f'SELECT DISTINCT "{column}" FROM read_parquet(?) WHERE "{column}" IS NOT NULL ORDER BY 1',
                [table["parquet_path"]],
            ).fetchall()
        values = [str(row[0]) for row in rows if str(row[0]).strip()]
        self._cache[key] = values
        return values

    def match_phrase(self, phrase: str, table: dict, column: str, top_k: int = 8) -> dict[str, Any]:
        values = self.unique_values(table, column)
        norm_to_value = {normalize_text(value): value for value in values}
        normalized_choices = list(norm_to_value)
        exact = [value for norm, value in norm_to_value.items() if norm and norm in normalize_text(phrase)]
        if exact:
            candidates = [{"value": value, "score": 1.0, "method": "substring"} for value in exact[:top_k]]
        else:
            matches = process.extract(normalize_text(phrase), normalized_choices, scorer=fuzz.token_set_ratio, limit=top_k)
            candidates = [{"value": norm_to_value[match], "score": round(score / 100, 3), "method": "fuzzy"} for match, score, _ in matches]
        best = candidates[0] if candidates else None
        final = [best["value"]] if best and best["score"] >= 0.90 else []
        confidence = best["score"] if best else 0.0
        payload = {
            "phrase": phrase,
            "column": column,
            "candidates": candidates,
            "llm_selection": None,
            "final_selection": final,
            "confidence": confidence,
        }
        self._log(payload)
        return payload

    def _log(self, payload: dict[str, Any]) -> None:
        self.artifacts_dir.mkdir(exist_ok=True)
        path = self.artifacts_dir / "semantic_matching_debug.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except json.JSONDecodeError:
            rows = []
        rows.append(payload)
        path.write_text(json.dumps(rows[-500:], ensure_ascii=False, indent=2), encoding="utf-8")


def categorical_columns(table: dict) -> list[str]:
    columns = []
    for col in table.get("columns", []):
        dtype = str(col.get("dtype", ""))
        if dtype == "object" and not col["normalized_name"].startswith("_"):
            columns.append(col["normalized_name"])
    return columns
