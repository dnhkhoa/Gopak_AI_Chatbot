"""Customer error policy benchmark (spec section 20).

Acceptance: customer error localization = 100% (Vietnamese), generic English
errors = 0, stack-trace leakage = 0. Covers every ErrorCode plus a live injected
exception path. Writes artifacts/customer_error_policy_results.json.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "2ad2989784fc41ffb9fef3225034db54"

VI_ACCENTS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵĂÂĐÊÔƠƯ")
ENGLISH_MARKERS = ["could not complete", "unable to", "the analysis service", "language model could not"]
STACK_MARKERS = ["Traceback", "Exception", "pydantic", "validation error for", "File \""]


def _has_accents(text: str) -> bool:
    return any(c in VI_ACCENTS for c in text)


def main() -> None:
    from src.config import Settings
    from src.application.chat_service import ChatApplicationService
    from src.application.errors import CustomerErrorMessagePolicy, ErrorCode

    results = []
    english = 0
    non_vietnamese = 0
    # 1. policy coverage for every code
    for code in ErrorCode:
        err = CustomerErrorMessagePolicy.build(code)
        text = f"{err.title} {err.message}"
        is_vi = _has_accents(text)
        has_english = any(m in text.lower() for m in ENGLISH_MARKERS)
        if not is_vi:
            non_vietnamese += 1
        if has_english:
            english += 1
        results.append({"source": "policy", "code": code.value, "vietnamese": is_vi, "english": has_english, "title": err.title})

    # 2. live injected exception -> classified, customer-safe, no stack leak
    tmp = tempfile.mkdtemp(prefix="gopak_err_")
    svc = ChatApplicationService(settings=Settings(memory_db_path=Path(tmp) / "err.db"))
    svc.get_catalog()
    convo = svc.create_conversation(title="err", source_file_id=ENTRY).id
    # monkeypatch the planner to raise, exercising the generic classifier path
    import src.application.chat_service as cs
    original = cs.QueryPlanner

    class _Boom:
        def __init__(self, *a, **k):
            pass

        def plan(self, *a, **k):
            raise RuntimeError("simulated boom: 1 validation error for MetricSpec column is required")

    cs.QueryPlanner = _Boom
    try:
        resp = svc.process_message(convo, "Cổng nào có giao dịch nhiều nhất theo thời gian xu huong?", source_file_id=ENTRY, debug=False)
    finally:
        cs.QueryPlanner = original
    public_text = f"{resp.title} {resp.summary}"
    stack_leak = any(m in public_text for m in STACK_MARKERS)
    is_vi = _has_accents(public_text)
    has_english = any(m in public_text.lower() for m in ENGLISH_MARKERS)
    if not is_vi:
        non_vietnamese += 1
    if has_english:
        english += 1
    results.append({
        "source": "live_injected_exception", "error_code": resp.metadata.get("error_code"),
        "vietnamese": is_vi, "english": has_english, "stack_leak": stack_leak,
        "summary": resp.summary,
    })

    stack_leaks = sum(1 for r in results if r.get("stack_leak"))
    total = len(results)
    localized = sum(1 for r in results if r["vietnamese"] and not r["english"])
    summary = {
        "total_checks": total,
        "customer_error_localization_pct": round(100 * localized / total, 1),
        "generic_english_errors": english,
        "non_vietnamese": non_vietnamese,
        "stack_trace_leakage": stack_leaks,
        "acceptance_met": english == 0 and non_vietnamese == 0 and stack_leaks == 0,
        "results": results,
    }
    out = ROOT / "artifacts" / "customer_error_policy_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
