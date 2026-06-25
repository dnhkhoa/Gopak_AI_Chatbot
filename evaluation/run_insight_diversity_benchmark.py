from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.overview_benchmark_utils import benchmark_cases
from src.application.overview_analysis import build_domain_aware_overview


def run() -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="gopak-insight-diversity-") as tmp:
        for case in benchmark_cases(Path(tmp)):
            brief = build_domain_aware_overview(case["catalog"])
            assert brief is not None
            insights = brief.selected_insights
            if case.get("insufficient"):
                passed = len(insights) <= 1
                results.append(
                    {
                        "id": case["id"],
                        "passed": passed,
                        "insight_count": len(insights),
                        "type_counts": {},
                        "metric_counts": {},
                        "entity_counts": {},
                        "selected": [],
                    }
                )
                continue
            type_counts = Counter(item.insight_type for item in insights)
            metric_counts = Counter(item.primary_metric for item in insights)
            entity_counts = Counter(item.primary_entity for item in insights if item.primary_entity)
            enough = len(insights) >= (1 if case.get("insufficient") else 2)
            pass_type = all(count <= 2 for count in type_counts.values())
            pass_metric = len(metric_counts) >= min(2, len(insights)) if len(insights) > 1 else True
            pass_entity = len(entity_counts) >= min(2, len([item for item in insights if item.primary_entity])) if len(entity_counts) else True
            passed = bool(enough and pass_type and pass_metric and pass_entity)
            results.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "insight_count": len(insights),
                    "type_counts": dict(type_counts),
                    "metric_counts": dict(metric_counts),
                    "entity_counts": dict(entity_counts),
                    "selected": [
                        {
                            "title": item.title,
                            "type": item.insight_type,
                            "metric": item.primary_metric,
                            "entity": item.primary_entity,
                        }
                        for item in insights
                    ],
                }
            )
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    artifact = {
        "summary": {
            "total": total,
            "passed": passed,
            "insight_diversity_pass_rate": passed / total if total else 0,
            "requested_insight_count_fulfillment": passed / total if total else 0,
            "status": "passed" if passed == total else "failed",
        },
        "results": results,
    }
    out = ROOT / "artifacts" / "insight_diversity_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(json.dumps(run()["summary"], ensure_ascii=False, indent=2))
