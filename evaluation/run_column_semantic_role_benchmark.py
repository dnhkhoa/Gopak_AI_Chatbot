from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.overview_benchmark_utils import benchmark_cases
from src.application.overview_analysis import classify_columns


def run() -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="gopak-column-role-") as tmp:
        for case in benchmark_cases(Path(tmp)):
            table = case["catalog"]["tables"][0]
            import pandas as pd

            df = pd.read_parquet(table["parquet_path"])
            profiles = classify_columns(table, df)
            technical_selected = [p.column_name for p in profiles if (p.is_row_index or p.is_identifier or p.is_technical_metadata) and p.is_measure]
            forbidden_roles = {
                p.column_name: p.semantic_role
                for p in profiles
                if p.column_name.lower() in {str(x).lower() for x in case.get("forbidden", [])}
            }
            passed = bool(forbidden_roles) if case.get("forbidden") else True
            passed = passed and not technical_selected
            results.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "forbidden_roles": forbidden_roles,
                    "technical_selected_as_measure": technical_selected,
                    "profiles": [p.model_dump() for p in profiles],
                }
            )
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    artifact = {
        "summary": {
            "total": total,
            "passed": passed,
            "technical_column_exclusion_rate": 1.0 if all(not item["technical_selected_as_measure"] for item in results) else 0.0,
            "identifier_exclusion_rate": passed / total if total else 0.0,
            "status": "passed" if passed == total else "failed",
        },
        "results": results,
    }
    out = ROOT / "artifacts" / "column_semantic_role_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(json.dumps(run()["summary"], ensure_ascii=False, indent=2))
