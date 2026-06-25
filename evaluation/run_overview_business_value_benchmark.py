from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.overview_benchmark_utils import benchmark_cases, insight_text
from src.application.overview_analysis import build_domain_aware_overview, human_usefulness_score, response_quality_errors, validate_overview_brief


def run() -> dict:
    results = []
    trivial_rejections = []
    with tempfile.TemporaryDirectory(prefix="gopak-overview-value-") as tmp:
        for case in benchmark_cases(Path(tmp)):
            brief = build_domain_aware_overview(case["catalog"])
            assert brief is not None
            text = insight_text(brief)
            forbidden_hits = [term for term in case.get("forbidden", []) if _has_forbidden_column(text, term)]
            required = case.get("required_terms", [])
            required_hit = any(term.lower() in text for term in required) if required else True
            quality = validate_overview_brief(brief)
            usefulness = human_usefulness_score(brief)
            filler = response_quality_errors(text)
            insufficient_ok = not case.get("insufficient") or len(brief.selected_insights) <= 1 or "insufficient_business_columns" in brief.quality_warnings
            quality_ok = quality["passed"] or bool(case.get("insufficient"))
            usefulness_threshold = 10 if case.get("insufficient") else 13
            passed = (
                not forbidden_hits
                and required_hit
                and quality_ok
                and not filler
                and insufficient_ok
                and usefulness["total"] >= usefulness_threshold
            )
            rejected = [
                {"case_id": case["id"], "reason": "forbidden_or_trivial", "terms": forbidden_hits}
            ] if forbidden_hits else []
            trivial_rejections.extend(rejected)
            results.append(
                {
                    "id": case["id"],
                    "expected_domain": case["domain"],
                    "actual_domain": brief.capability_profile.selected_domain,
                    "passed": passed,
                    "forbidden_hits": forbidden_hits,
                    "required_hit": required_hit,
                    "quality": quality,
                    "human_usefulness": usefulness,
                    "selected_insights": [item.model_dump() for item in brief.selected_insights],
                    "warnings": brief.quality_warnings,
                    "filler_errors": filler,
                }
            )
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    scores = [item["human_usefulness"]["total"] for item in results]
    evidence_covered = all(
        item["quality"]["passed"] or (item["id"] == "insufficient" and not item["selected_insights"])
        for item in results
    )
    artifact = {
        "summary": {
            "total": total,
            "passed": passed,
            "technical_column_exclusion_rate": 1.0 if all(not item["forbidden_hits"] for item in results) else 0.0,
            "business_metric_inclusion_rate": 1.0 if all(item["required_hit"] for item in results if item["id"] != "insufficient") else 0.0,
            "domain_relevance_rate": sum(1 for item in results if item["actual_domain"] == item["expected_domain"] or item["expected_domain"] == "generic_tabular") / total,
            "evidence_coverage": 1.0 if evidence_covered else 0.0,
            "generic_filler_rate": sum(1 for item in results if item["filler_errors"]) / total,
            "trivial_insight_rate": sum(1 for item in results if item["forbidden_hits"]) / total,
            "average_human_usefulness": round(sum(scores) / len(scores), 2) if scores else 0,
            "min_human_usefulness": min(scores) if scores else 0,
            "status": "passed" if passed == total and (sum(scores) / len(scores)) >= 13 and min(scores) >= 10 else "failed",
        },
        "results": results,
    }
    out = ROOT / "artifacts" / "overview_business_value_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ROOT / "artifacts" / "trivial_insight_rejections.json").write_text(json.dumps(trivial_rejections, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def _has_forbidden_column(text: str, term: str) -> bool:
    import re

    token = re.escape(str(term).lower())
    if len(term) <= 3:
        return re.search(rf"(?<![a-z0-9_]){token}(?![a-z0-9_])", text) is not None
    return token in text


if __name__ == "__main__":
    print(json.dumps(run()["summary"], ensure_ascii=False, indent=2))
