"""Localization contract benchmark (spec section 20).

Acceptance: Vietnamese diacritic preservation = 100%, internal field leakage = 0,
across deterministic response paths (overview, scalar, capability-refusal, error,
History reload). Writes artifacts/localization_contract_results.json.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "2ad2989784fc41ffb9fef3225034db54"
DOWNTIME = "e385c6e2a4ff41a8baf63f323dfc0b59"

PROBES = [
    (ENTRY, "Phân tích dữ liệu này và cho tôi ba phát hiện quan trọng nhất."),
    (ENTRY, "File có bao nhiêu bản ghi?"),
    (ENTRY, "Máy nào có tổng downtime cao nhất?"),  # capability refusal
    (DOWNTIME, "Máy nào có tổng downtime cao nhất?"),
    (DOWNTIME, "Phân tích xu hướng downtime theo thời gian."),
]


def _blob(resp) -> str:
    parts = [resp.title, resp.summary, resp.primary_value, resp.secondary_value]
    if resp.table:
        parts.extend(resp.table.columns)
    if resp.chart:
        parts.append(resp.chart.title)
    return " ".join(str(p or "") for p in parts)


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="gopak_loc_")
    from src.config import Settings
    from src.application.chat_service import ChatApplicationService
    from src.rendering.labels import find_internal_keys, find_unaccented_vietnamese

    svc = ChatApplicationService(settings=Settings(memory_db_path=Path(tmp) / "loc.db"))
    svc.get_catalog()

    results = []
    leak_count = 0
    for file_id, message in PROBES:
        convo = svc.create_conversation(title="loc", source_file_id=file_id).id
        resp = svc.process_message(convo, message, source_file_id=file_id)
        blob = _blob(resp)
        keys = find_internal_keys(blob)
        unacc = find_unaccented_vietnamese(blob)
        # History reload check
        detail = svc.get_conversation(convo)
        hist_blob = " ".join(_blob(m.response) for m in detail.messages if m.response)
        hist_keys = find_internal_keys(hist_blob)
        hist_unacc = find_unaccented_vietnamese(hist_blob)
        clean = not (keys or unacc or hist_keys or hist_unacc)
        if not clean:
            leak_count += 1
        results.append({
            "file_id": file_id, "message": message, "response_type": resp.response_type,
            "internal_keys": keys, "unaccented": unacc,
            "history_internal_keys": hist_keys, "history_unaccented": hist_unacc,
            "clean": clean,
        })

    total = len(results)
    passed = sum(1 for r in results if r["clean"])
    summary = {
        "total_probes": total,
        "clean": passed,
        "diacritic_preservation_pct": round(100 * passed / total, 1) if total else 100.0,
        "internal_field_leakage": leak_count,
        "acceptance_met": leak_count == 0 and passed == total,
        "results": results,
    }
    out = ROOT / "artifacts" / "localization_contract_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
