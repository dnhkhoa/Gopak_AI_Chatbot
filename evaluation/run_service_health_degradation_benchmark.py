"""Service health degradation benchmark (spec section 20).

Acceptance: schema mismatch causing degraded health = 0; a model outage does not
flip the global infrastructure banner; health is layered. Writes
artifacts/service_health_degradation_results.json.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "2ad2989784fc41ffb9fef3225034db54"


def main() -> None:
    from src.config import Settings
    from src.application.chat_service import ChatApplicationService

    tmp = tempfile.mkdtemp(prefix="gopak_health_")
    svc = ChatApplicationService(settings=Settings(memory_db_path=Path(tmp) / "health.db"))
    svc.get_catalog()

    checks = []

    # 1. schema mismatch (downtime on transaction file) must not change health
    before = svc.health()
    convo = svc.create_conversation(title="health", source_file_id=ENTRY).id
    svc.process_message(convo, "Máy nào có tổng downtime cao nhất?", source_file_id=ENTRY)
    after = svc.health()
    schema_mismatch_changed_health = before.infrastructure_degraded != after.infrastructure_degraded or after.infrastructure_degraded
    checks.append({
        "check": "schema_mismatch_keeps_health",
        "infra_degraded_before": before.infrastructure_degraded,
        "infra_degraded_after": after.infrastructure_degraded,
        "passed": not schema_mismatch_changed_health,
    })

    # 2. simulate model outage -> language_model UNAVAILABLE but infra NOT degraded
    import src.application.chat_service as cs
    original = cs.OllamaClient

    class _DownOllama:
        def __init__(self, *a, **k):
            pass

        def health(self):
            return {"ok": False}

    cs.OllamaClient = _DownOllama
    try:
        degraded_model = svc.health()
    finally:
        cs.OllamaClient = original
    model_outage_ok = (
        degraded_model.language_model_available is False
        and degraded_model.components.language_model == "UNAVAILABLE"
        and degraded_model.infrastructure_degraded is False
        and degraded_model.banner_message is None
        and bool(degraded_model.language_model_note)
    )
    checks.append({
        "check": "model_outage_does_not_flip_infra_banner",
        "language_model": degraded_model.components.language_model,
        "infrastructure_degraded": degraded_model.infrastructure_degraded,
        "banner_message": degraded_model.banner_message,
        "language_model_note_present": bool(degraded_model.language_model_note),
        "passed": model_outage_ok,
    })

    # 3. health is layered
    h = svc.health()
    layered_ok = h.components is not None and h.components.core_api == "HEALTHY"
    checks.append({"check": "health_is_layered", "components": h.components.model_dump(), "passed": layered_ok})

    schema_mismatch_degraded_count = 0 if checks[0]["passed"] else 1
    summary = {
        "schema_mismatch_causing_degraded_health": schema_mismatch_degraded_count,
        "all_checks_passed": all(c["passed"] for c in checks),
        "acceptance_met": all(c["passed"] for c in checks),
        "checks": checks,
    }
    out = ROOT / "artifacts" / "service_health_degradation_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "checks"}, ensure_ascii=False, indent=2))
    for c in checks:
        print(" ", c["check"], "->", "PASS" if c["passed"] else "FAIL")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
