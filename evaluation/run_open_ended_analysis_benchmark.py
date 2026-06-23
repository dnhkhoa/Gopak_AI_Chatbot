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
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files

ARTIFACTS = ROOT / "artifacts"
QUESTION = "Dựa trên toàn bộ dữ liệu, hãy giải thích ba điểm đáng chú ý nhất, so sánh chúng và nêu giới hạn của kết luận."


def _record(files: list[dict[str, Any]], needle: str) -> dict[str, Any]:
    return next(item for item in files if needle in str(item.get("filename", "")) and item.get("status") == "ready")


def run(phase: str = "final") -> dict[str, Any]:
    settings = get_settings()
    files = list_uploaded_files()
    cases = [
        {"id": "open_ended_exact_machine", "file": "Machine_Downtime", "message": QUESTION},
    ]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gopak-open-ended-", ignore_cleanup_errors=True) as tmp:
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
            text = response.summary or ""
            answer_brief = response.metadata.get("answer_brief") if isinstance(response.metadata, dict) else None
            checks = {
                "not_clarification": response.response_type != "clarification",
                "has_answer_brief": isinstance(answer_brief, dict) and bool(answer_brief.get("selected_insights")),
                "has_three_points": text.count("- ") >= 3 or "ba điểm" in text.lower(),
                "has_comparison": "So sánh" in text or "so sánh" in text.lower(),
                "has_limitations": "Giới hạn" in text or "giới hạn" in text.lower(),
                "no_internal_terms": not any(term in text.lower() for term in ["context json", "answerbrief", "null", "fallback", "planner"]),
                "composer_validated": bool(response.metadata.get("composer_validation_passed")),
            }
            results.append(
                {
                    "id": case["id"],
                    "message": case["message"],
                    "response_type": response.response_type,
                    "summary": text,
                    "table": response.table.model_dump(mode="json") if response.table else None,
                    "metadata": response.metadata,
                    "checks": checks,
                    "passed": all(checks.values()),
                }
            )
    summary = {
        "phase": phase,
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
    }
    payload = {"summary": summary, "results": results}
    ARTIFACTS.mkdir(exist_ok=True)
    name = "open_ended_analysis_baseline.json" if phase == "baseline" else "open_ended_analysis_final_results.json"
    (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["baseline", "final"], default="final")
    args = parser.parse_args()
    payload = run(args.phase)
    return 0 if payload["summary"]["passed"] == payload["summary"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
