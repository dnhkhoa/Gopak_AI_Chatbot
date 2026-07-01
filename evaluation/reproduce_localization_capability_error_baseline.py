"""Reproduce the P0 localization/capability/error baseline (spec section 4).

Runs the four UAT turns against the EntryTransaction file using the in-process
ChatApplicationService (public surface), capturing for each turn: active file,
resolved intent, capability result, internal error code, public response, and
service health before/after. Writes artifacts/localization_capability_error_baseline.json.

Uses an isolated temp memory DB so it does not touch the live app DB.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY_TRANSACTION = "2ad2989784fc41ffb9fef3225034db54"

TURNS = [
    "Phân tích dữ liệu này và cho tôi ba phát hiện quan trọng nhất.",
    "Máy nào có tổng downtime cao nhất?",
    "Phân tích xu hướng downtime theo thời gian.",
    "Tạo báo cáo tổng quan.",
]


def _health(service) -> dict:
    try:
        return service.health().model_dump()
    except Exception as exc:  # pragma: no cover - diagnostic
        return {"error": repr(exc)}


def _response_public(resp) -> dict:
    return {
        "response_type": resp.response_type,
        "title": resp.title,
        "summary": resp.summary,
        "primary_value": resp.primary_value,
        "table_columns": (resp.table.columns if resp.table else None),
        "chart_title": (resp.chart.title if resp.chart else None),
        "error_code": resp.metadata.get("error_code"),
        "execution_mode": resp.metadata.get("execution_mode") or resp.metadata.get("mode"),
        "llm_called": resp.metadata.get("llm_called"),
        "capability": resp.metadata.get("capability"),
        "file_scope_validated": resp.metadata.get("file_scope_validated"),
    }


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="gopak_baseline_")
    os.environ["MEMORY_DB_PATH"] = str(Path(tmp) / "baseline.db")
    # Fresh settings after env override
    from src.config import Settings
    from src.application.chat_service import ChatApplicationService

    service = ChatApplicationService(settings=Settings(memory_db_path=Path(os.environ["MEMORY_DB_PATH"])) )
    service.get_catalog()

    convo = service.create_conversation(title="Baseline EntryTransaction", source_file_id=ENTRY_TRANSACTION)
    conversation_id = convo.id

    records = []
    for idx, message in enumerate(TURNS, start=1):
        health_before = _health(service)
        intent = None
        error_code = None
        try:
            from src.application.customer_intents import detect_customer_intent

            intent = detect_customer_intent(message).intent
        except Exception:
            intent = None
        try:
            resp = service.process_message(conversation_id, message, debug=True, source_file_id=ENTRY_TRANSACTION)
            public = _response_public(resp)
        except Exception as exc:  # pragma: no cover - diagnostic
            public = {"raised": repr(exc)}
        health_after = _health(service)
        records.append(
            {
                "turn": idx,
                "active_file": ENTRY_TRANSACTION,
                "request": message,
                "resolved_intent": intent,
                "public_response": public,
                "health_before": health_before,
                "health_after": health_after,
            }
        )
        print(f"--- Turn {idx}: {message}")
        print(json.dumps(public, ensure_ascii=False, indent=2))

    out = ROOT / "artifacts" / "localization_capability_error_baseline.json"
    out.write_text(json.dumps({"conversation_id": conversation_id, "turns": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
