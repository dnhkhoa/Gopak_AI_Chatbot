"""Active-file capability benchmark (spec section 20).

Acceptance: unsupported active-file classification = 100%, wrong-file SQL = 0,
wrong-file LLM composer calls = 0. Writes artifacts/active_file_capability_results.json.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "2ad2989784fc41ffb9fef3225034db54"
LOSS = "a329169db4984cab80ed5fea5880bb4f"
DOWNTIME = "e385c6e2a4ff41a8baf63f323dfc0b59"

# (file_id, message, expect_unsupported)
CASES = [
    (ENTRY, "Máy nào có tổng downtime cao nhất?", True),
    (ENTRY, "Phân tích xu hướng downtime theo thời gian.", True),
    (ENTRY, "Nhóm tổn thất nào có tổng downtime lớn nhất?", True),
    (ENTRY, "Phân tích dữ liệu này.", False),
    (ENTRY, "File có bao nhiêu bản ghi?", False),
    (DOWNTIME, "Máy nào có tổng downtime cao nhất?", False),
    (DOWNTIME, "Phân tích xu hướng downtime theo thời gian.", False),
    (LOSS, "Nhóm tổn thất nào có tổng downtime lớn nhất?", False),
]


def main() -> None:
    from src.config import Settings
    from src.application.chat_service import ChatApplicationService
    from src.application.errors import ErrorCode

    tmp = tempfile.mkdtemp(prefix="gopak_cap_")
    svc = ChatApplicationService(settings=Settings(memory_db_path=Path(tmp) / "cap.db"))
    svc.get_catalog()

    results = []
    correct = 0
    wrong_file_sql = 0
    wrong_file_llm = 0
    for file_id, message, expect_unsupported in CASES:
        convo = svc.create_conversation(title="cap", source_file_id=file_id).id
        resp = svc.process_message(convo, message, source_file_id=file_id)
        code = resp.metadata.get("error_code")
        is_unsupported = code == ErrorCode.UNSUPPORTED_BY_ACTIVE_FILE.value
        ok = is_unsupported == expect_unsupported
        correct += int(ok)
        if expect_unsupported:
            if resp.metadata.get("generated_sql"):
                wrong_file_sql += 1
            if resp.metadata.get("llm_called"):
                wrong_file_llm += 1
        results.append({
            "file_id": file_id, "message": message,
            "expected_unsupported": expect_unsupported,
            "classified_unsupported": is_unsupported,
            "error_code": code,
            "llm_called": resp.metadata.get("llm_called"),
            "generated_sql": bool(resp.metadata.get("generated_sql")),
            "recommended_file": (resp.metadata.get("capability") or {}).get("recommended_file_name"),
            "correct": ok,
        })

    total = len(CASES)
    summary = {
        "total_cases": total,
        "correct_classifications": correct,
        "classification_pct": round(100 * correct / total, 1),
        "wrong_file_sql_executions": wrong_file_sql,
        "wrong_file_llm_calls": wrong_file_llm,
        "acceptance_met": correct == total and wrong_file_sql == 0 and wrong_file_llm == 0,
        "results": results,
    }
    out = ROOT / "artifacts" / "active_file_capability_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
