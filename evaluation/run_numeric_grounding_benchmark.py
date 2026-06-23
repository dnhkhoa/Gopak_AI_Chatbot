from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.application.grounding import AllowedNumericFact, GroundedComposerValidator
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files

ARTIFACTS = ROOT / "artifacts"


def _record(files: list[dict[str, Any]], needle: str) -> dict[str, Any]:
    return next(item for item in files if needle in str(item.get("filename", "")) and item.get("status") == "ready")


def _table_text(response: Any) -> str:
    return json.dumps(response.table.model_dump(mode="json") if response.table else {}, ensure_ascii=False).lower()


def _commentary_text(response: Any) -> str:
    text = response.summary or ""
    marker = "Nhận xét:"
    return text.split(marker, 1)[1] if marker in text else text


def _forbidden_numeric_claims(text: str) -> list[str]:
    lowered = text.lower()
    bad = []
    for phrase in ["69 lần", "1.600", "1600", "27 ngày", "28 ngày", "gần một nửa", "một nửa", "tương đương 27", "tương đương 28"]:
        if phrase in lowered:
            bad.append(phrase)
    return bad


def _synthetic_validator_cases() -> list[dict[str, Any]]:
    validator = GroundedComposerValidator(
        [
            AllowedNumericFact("machine", 11, "11"),
            AllowedNumericFact("duration", 413.57, "413,57 giờ"),
            AllowedNumericFact("count", 1469, "1.469"),
            AllowedNumericFact("avg", 16, "16 phút 54 giây"),
            AllowedNumericFact("pct", 74.06, "74,06%"),
        ]
    )
    cases = [
        ("reject_wrong_count", "Máy 11 có khoảng 69 lần dừng.", False),
        ("reject_bad_conversion", "1.600 lần tương đương 27 ngày.", False),
        ("reject_unsupported_share", "Nhóm này gần một nửa tổng kết quả.", False),
        ("accept_displayed_values", "Máy 11 có 413,57 giờ, 1.469 lần ghi nhận và trung bình 16 phút 54 giây.", True),
        ("accept_percent", "Sản xuất có tỷ lệ 74,06%.", True),
    ]
    results = []
    for case_id, text, expected in cases:
        validation = validator.validate(text)
        results.append({"id": case_id, "text": text, "expected": expected, "passed": validation.passed == expected, "errors": validation.errors})
    return results


def run(phase: str = "final") -> dict[str, Any]:
    settings = get_settings()
    files = list_uploaded_files()
    cases = [
        {
            "id": "top_groups_percent_commentary",
            "file": "Loss_Assignment",
            "message": "Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét.",
            "checks": ["percentage", "commentary", "vietnamese_columns"],
        },
        {
            "id": "top_machines_full_commentary",
            "file": "Machine_Downtime",
            "message": "Top 5 máy theo tổng downtime, thêm số lần dừng, thời lượng trung bình và giải thích điểm khác biệt.",
            "checks": ["count_metric", "avg_metric", "commentary", "vietnamese_columns"],
        },
    ]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gopak-numeric-grounding-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        for case in cases:
            record = _record(files, case["file"])
            conversation = app.create_conversation(case["id"], source_file_id=str(record["id"]))
            response = app.process_message(conversation.id, case["message"], debug=True, source_file_id=str(record["id"]))
            table_text = _table_text(response)
            commentary = _commentary_text(response)
            checks = {
                "table": bool(response.table and response.table.rows),
                "commentary": "nhận xét" in (response.summary or "").lower(),
                "composer_validated": bool(response.metadata.get("composer_validation_passed")),
                "no_forbidden_numeric_claims": not _forbidden_numeric_claims(commentary),
                "percentage": "%" in table_text if "percentage" in case["checks"] else True,
                "count_metric": "số lần" in table_text or "ghi nhận" in table_text if "count_metric" in case["checks"] else True,
                "avg_metric": "trung bình" in table_text if "avg_metric" in case["checks"] else True,
                "vietnamese_columns": not any(term in table_text for term in ["stop count", "average duration", "total count", "percentage"]),
            }
            entry = {
                "id": case["id"],
                "message": case["message"],
                "response_type": response.response_type,
                "summary": response.summary,
                "table": response.table.model_dump(mode="json") if response.table else None,
                "metadata": response.metadata,
                "checks": checks,
                "passed": all(checks.values()),
                "forbidden_claims": _forbidden_numeric_claims(commentary),
            }
            if not entry["passed"]:
                failures.append(entry)
            results.append(entry)
    synthetic = _synthetic_validator_cases()
    failures.extend(item for item in synthetic if not item["passed"])
    summary = {
        "phase": phase,
        "total": len(results) + len(synthetic),
        "passed": sum(1 for item in results if item["passed"]) + sum(1 for item in synthetic if item["passed"]),
        "response_cases": len(results),
        "synthetic_cases": len(synthetic),
        "failure_count": len(failures),
    }
    summary["accuracy"] = round(summary["passed"] / max(1, summary["total"]), 4)
    payload = {"summary": summary, "results": results, "synthetic_validator_cases": synthetic}
    ARTIFACTS.mkdir(exist_ok=True)
    name = "numeric_grounding_baseline.json" if phase == "baseline" else "numeric_grounding_final_results.json"
    (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "composer_validation_failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["baseline", "final"], default="final")
    args = parser.parse_args()
    payload = run(args.phase)
    return 0 if payload["summary"]["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
