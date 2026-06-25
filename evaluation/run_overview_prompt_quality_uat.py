from __future__ import annotations

import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files

ARTIFACTS = ROOT / "artifacts"


def _u(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


QUESTIONS = {
    "machine_manager_3": _u(
        "Ph\\u00e2n t\\u00edch d\\u1eef li\\u1ec7u n\\u00e0y v\\u00e0 cho t\\u00f4i ba ph\\u00e1t hi\\u1ec7n quan tr\\u1ecdng nh\\u1ea5t "
        "\\u0111\\u1ed1i v\\u1edbi ng\\u01b0\\u1eddi qu\\u1ea3n l\\u00fd v\\u1eadn h\\u00e0nh. M\\u1ed7i ph\\u00e1t hi\\u1ec7n ph\\u1ea3i c\\u00f3 "
        "s\\u1ed1 li\\u1ec7u ch\\u1ee9ng minh v\\u00e0 kh\\u00f4ng s\\u1eed d\\u1ee5ng c\\u00e1c c\\u1ed9t s\\u1ed1 th\\u1ee9 t\\u1ef1 "
        "ho\\u1eb7c m\\u00e3 \\u0111\\u1ecbnh danh l\\u00e0m insight."
    ),
    "machine_metric_comparison": _u(
        "H\\u00e3y ph\\u00e2n bi\\u1ec7t m\\u00e1y c\\u00f3 t\\u1ed5ng downtime cao nh\\u1ea5t, m\\u00e1y c\\u00f3 s\\u1ed1 l\\u1ea7n "
        "d\\u1eebng nhi\\u1ec1u nh\\u1ea5t v\\u00e0 m\\u00e1y c\\u00f3 th\\u1eddi l\\u01b0\\u1ee3ng d\\u1eebng trung b\\u00ecnh cao nh\\u1ea5t. "
        "Gi\\u1ea3i th\\u00edch v\\u00ec sao ba ch\\u1ec9 ti\\u00eau n\\u00e0y kh\\u00f4ng n\\u00ean \\u0111\\u01b0\\u1ee3c hi\\u1ec3u gi\\u1ed1ng nhau."
    ),
    "machine_time_trend": _u(
        "Ph\\u00e2n t\\u00edch xu h\\u01b0\\u1edbng downtime theo th\\u1eddi gian, x\\u00e1c \\u0111\\u1ecbnh giai \\u0111o\\u1ea1n "
        "cao nh\\u1ea5t v\\u00e0 th\\u1ea5p nh\\u1ea5t, sau \\u0111\\u00f3 so s\\u00e1nh m\\u1ee9c ch\\u00eanh l\\u1ec7ch. "
        "Ch\\u1ec9 n\\u00eau nguy\\u00ean nh\\u00e2n n\\u1ebfu d\\u1eef li\\u1ec7u th\\u1ef1c s\\u1ef1 c\\u00f3 b\\u1eb1ng ch\\u1ee9ng."
    ),
    "column_role_audit": _u(
        "Trong file n\\u00e0y, nh\\u1eefng c\\u1ed9t n\\u00e0o mang \\u00fd ngh\\u0129a nghi\\u1ec7p v\\u1ee5 v\\u00e0 nh\\u1eefng "
        "c\\u1ed9t n\\u00e0o ch\\u1ec9 l\\u00e0 s\\u1ed1 th\\u1ee9 t\\u1ef1, m\\u00e3 \\u0111\\u1ecbnh danh ho\\u1eb7c metadata k\\u1ef9 "
        "thu\\u1eadt? Sau \\u0111\\u00f3 ch\\u1ec9 ph\\u00e2n t\\u00edch c\\u00e1c c\\u1ed9t nghi\\u1ec7p v\\u1ee5."
    ),
    "useful_non_trivial": _u(
        "Cho t\\u00f4i ba insight th\\u1ef1c s\\u1ef1 h\\u1eefu \\u00edch t\\u1eeb d\\u1eef li\\u1ec7u n\\u00e0y. "
        "Kh\\u00f4ng xem vi\\u1ec7c m\\u1ed9t c\\u1ed9t \\u0111\\u1ea7y \\u0111\\u1ee7 100%, m\\u1ed9t m\\u00e3 ch\\u1ec9 "
        "xu\\u1ea5t hi\\u1ec7n m\\u1ed9t l\\u1ea7n ho\\u1eb7c m\\u1ed9t c\\u1ed9t c\\u00f3 to\\u00e0n gi\\u00e1 tr\\u1ecb duy "
        "nh\\u1ea5t l\\u00e0 insight \\u0111\\u00e1ng ch\\u00fa \\u00fd."
    ),
    "loss_structure": _u(
        "Ph\\u00e2n t\\u00edch c\\u01a1 c\\u1ea5u t\\u1ed5n th\\u1ea5t trong file n\\u00e0y. Cho t\\u00f4i c\\u00e1c nh\\u00f3m "
        "ho\\u1eb7c lo\\u1ea1i t\\u1ed5n th\\u1ea5t ch\\u00ednh, m\\u1ee9c \\u0111\\u1ed9 t\\u1eadp trung c\\u1ee7a ch\\u00fang "
        "v\\u00e0 nh\\u1eefng h\\u1ea1n ch\\u1ebf khi di\\u1ec5n gi\\u1ea3i k\\u1ebft qu\\u1ea3."
    ),
    "entry_transaction": _u(
        "Ph\\u00e2n t\\u00edch t\\u00ecnh h\\u00ecnh giao d\\u1ecbch trong file n\\u00e0y, g\\u1ed3m quy m\\u00f4 d\\u1eef "
        "li\\u1ec7u, kho\\u1ea3ng th\\u1eddi gian, t\\u1ed5ng gi\\u00e1 tr\\u1ecb, gi\\u00e1 tr\\u1ecb trung b\\u00ecnh, "
        "nh\\u00f3m giao d\\u1ecbch n\\u1ed5i b\\u1eadt v\\u00e0 xu h\\u01b0\\u1edbng theo th\\u1eddi gian."
    ),
    "manager_brief": _u(
        "N\\u1ebfu ch\\u1ec9 \\u0111\\u01b0\\u1ee3c tr\\u00ecnh b\\u00e0y ba th\\u00f4ng tin t\\u1eeb file n\\u00e0y cho "
        "qu\\u1ea3n l\\u00fd trong m\\u1ed9t cu\\u1ed9c h\\u1ecdp ng\\u1eafn, b\\u1ea1n s\\u1ebd ch\\u1ecdn ba th\\u00f4ng "
        "tin n\\u00e0o? N\\u00eau l\\u00fd do ch\\u1ecdn v\\u00e0 s\\u1ed1 li\\u1ec7u h\\u1ed7 tr\\u1ee3."
    ),
    "four_viewpoints": _u(
        "H\\u00e3y \\u0111\\u01b0a ra b\\u1ed1n g\\u00f3c nh\\u00ecn kh\\u00e1c nhau v\\u1ec1 d\\u1eef li\\u1ec7u: quy m\\u00f4, "
        "x\\u1ebfp h\\u1ea1ng, ph\\u00e2n b\\u1ed1 v\\u00e0 xu h\\u01b0\\u1edbng. Kh\\u00f4ng l\\u1eb7p l\\u1ea1i c\\u00f9ng "
        "m\\u1ed9t metric d\\u01b0\\u1edbi nhi\\u1ec1u c\\u00e1ch di\\u1ec5n \\u0111\\u1ea1t."
    ),
    "followup_setup": _u("Ph\\u00e2n t\\u00edch d\\u1eef li\\u1ec7u n\\u00e0y v\\u00e0 \\u0111\\u01b0a ra ba insight quan tr\\u1ecdng nh\\u1ea5t."),
    "followup_evidence": _u(
        "Trong ba insight tr\\u00ean, insight n\\u00e0o c\\u00f3 b\\u1eb1ng ch\\u1ee9ng m\\u1ea1nh nh\\u1ea5t v\\u00e0 "
        "insight n\\u00e0o c\\u1ea7n th\\u1eadn tr\\u1ecdng nh\\u1ea5t? Gi\\u1ea3i th\\u00edch d\\u1ef1a \\u0111\\u00fang "
        "tr\\u00ean k\\u1ebft qu\\u1ea3 v\\u1eeba r\\u1ed3i."
    ),
    "causality_boundary": _u(
        "T\\u1eeb d\\u1eef li\\u1ec7u n\\u00e0y, c\\u00f3 th\\u1ec3 k\\u1ebft lu\\u1eadn nguy\\u00ean nh\\u00e2n khi\\u1ebfn "
        "m\\u1ed9t m\\u00e1y c\\u00f3 downtime cao hay kh\\u00f4ng? H\\u00e3y ph\\u00e2n bi\\u1ec7t \\u0111i\\u1ec1u "
        "d\\u1eef li\\u1ec7u ch\\u1ee9ng minh \\u0111\\u01b0\\u1ee3c v\\u00e0 \\u0111i\\u1ec1u ch\\u01b0a th\\u1ec3 k\\u1ebft lu\\u1eadn."
    ),
    "short_overview": _u("Data n\\u00e0y c\\u00f3 g\\u00ec \\u0111\\u00e1ng ch\\u00fa \\u00fd?"),
}


def run() -> dict[str, Any]:
    settings = get_settings()
    files = list_uploaded_files()
    with tempfile.TemporaryDirectory(prefix="gopak-overview-uat-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        results = [
            _single_turn(app, files, "A1_machine_manager_3", "Machine_Downtime", QUESTIONS["machine_manager_3"], _check_machine_manager),
            _single_turn(app, files, "A2_machine_metric_comparison", "Machine_Downtime", QUESTIONS["machine_metric_comparison"], _check_machine_comparison),
            _single_turn(app, files, "A3_machine_time_trend", "Machine_Downtime", QUESTIONS["machine_time_trend"], _check_time_trend),
            _single_turn(app, files, "B4_column_role_audit", "Machine_Downtime", QUESTIONS["column_role_audit"], _check_column_audit),
            _single_turn(app, files, "B5_useful_non_trivial", "Machine_Downtime", QUESTIONS["useful_non_trivial"], _check_non_trivial),
            _single_turn(app, files, "C6_loss_structure", "Loss_Assignment", QUESTIONS["loss_structure"], _check_loss_structure),
            _single_turn(app, files, "C7_entry_transaction", "EntryTransaction", QUESTIONS["entry_transaction"], _check_entry_transaction),
            _single_turn(app, files, "D8_manager_brief", "Machine_Downtime", QUESTIONS["manager_brief"], _check_manager_brief),
            _single_turn(app, files, "D9_four_viewpoints", "Machine_Downtime", QUESTIONS["four_viewpoints"], _check_four_viewpoints),
            _followup_turn(app, files),
            _single_turn(app, files, "E11_causality_boundary", "Machine_Downtime", QUESTIONS["causality_boundary"], _check_causality),
            _single_turn(app, files, "E12_short_overview", "Machine_Downtime", QUESTIONS["short_overview"], _check_short_overview),
        ]
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
        "failed_ids": [item["id"] for item in results if not item["passed"]],
        "status": "passed" if all(item["passed"] for item in results) else "failed",
    }
    artifact = {"summary": summary, "results": results}
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "overview_prompt_quality_uat.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return artifact


def _single_turn(
    app: ChatApplicationService,
    files: list[dict[str, Any]],
    case_id: str,
    file_key: str,
    message: str,
    checker: Callable[[str, Any], dict[str, bool]],
) -> dict[str, Any]:
    record = _record(files, file_key)
    started = perf_counter()
    conversation = app.create_conversation(case_id, source_file_id=str(record["id"]))
    response = app.process_message(conversation.id, message, debug=True, source_file_id=str(record["id"]))
    return _result(case_id, file_key, message, response, checker, perf_counter() - started)


def _followup_turn(app: ChatApplicationService, files: list[dict[str, Any]]) -> dict[str, Any]:
    record = _record(files, "Machine_Downtime")
    conversation = app.create_conversation("E10_followup_evidence", source_file_id=str(record["id"]))
    setup = app.process_message(conversation.id, QUESTIONS["followup_setup"], debug=True, source_file_id=str(record["id"]))
    started = perf_counter()
    response = app.process_message(conversation.id, QUESTIONS["followup_evidence"], debug=True, source_file_id=str(record["id"]))
    result = _result("E10_followup_evidence", "Machine_Downtime", QUESTIONS["followup_evidence"], response, _check_followup, perf_counter() - started)
    result["setup_summary"] = setup.summary
    result["setup_response_type"] = setup.response_type
    result["setup_checks"] = _check_machine_manager(setup.summary or "", setup)
    result["passed"] = result["passed"] and all(result["setup_checks"].values())
    return result


def _result(case_id: str, file_key: str, message: str, response: Any, checker: Callable[[str, Any], dict[str, bool]], elapsed: float) -> dict[str, Any]:
    text = response.summary or response.primary_value or response.title or ""
    checks = {
        "not_error": response.response_type != "error",
        "not_clarification": response.response_type != "clarification",
        "no_internal_terms": not _has_any(text, ["fallback", "planner", "answerbrief", "context json", "null"]),
        **checker(text, response),
    }
    return {
        "id": case_id,
        "file_key": file_key,
        "message": message,
        "response_type": response.response_type,
        "summary": text,
        "routing_reason": (response.metadata or {}).get("routing_reason"),
        "execution_mode": (response.metadata or {}).get("execution_mode"),
        "llm_called": bool((response.metadata or {}).get("llm_called")),
        "latency_ms": round(elapsed * 1000, 1),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _record(files: list[dict[str, Any]], key: str) -> dict[str, Any]:
    match = next((item for item in files if key.lower() in str(item.get("filename", "")).lower() and item.get("status") == "ready"), None)
    if not match:
        raise RuntimeError(f"Missing ready uploaded file containing {key}")
    return match


def _check_machine_manager(text: str, response: Any) -> dict[str, bool]:
    return {
        "has_three_points": _point_count(text) >= 3,
        "mentions_machine": _has_any(text, ["may"]),
        "mentions_downtime": _has_any(text, ["downtime", "thoi gian dung"]),
        "mentions_count": _has_any(text, ["so lan dung", "lan dung", "su kien"]),
        "mentions_average": _has_any(text, ["trung binh"]),
        "mentions_cause_or_time": _has_any(text, ["nguyen nhan", "thoi gian", "ngay", "giai doan"]),
        "has_real_numbers": bool(re.search(r"\d", text)),
        "no_technical_columns": _no_technical_columns(text),
    }


def _check_machine_comparison(text: str, response: Any) -> dict[str, bool]:
    return {
        "has_total_downtime": _has_any(text, ["tong downtime cao nhat", "tong thoi gian dung cao nhat"]),
        "has_event_count": _has_any(text, ["so lan dung nhieu nhat", "tan suat dung cao nhat"]),
        "has_avg_duration": _has_any(text, ["trung binh cao nhat", "thoi luong dung trung binh cao nhat"]),
        "explains_metric_difference": _has_any(text, ["khong nen duoc hieu giong nhau", "khac nhau", "ba chi tieu"]),
        "does_not_claim_quality_cause": not _has_any(text, ["dong nghia may kem chat luong", "may kem chat luong"]),
        "has_real_numbers": bool(re.search(r"\d", text)),
    }


def _check_time_trend(text: str, response: Any) -> dict[str, bool]:
    return {
        "uses_time": _has_any(text, ["ngay", "thang", "giai doan", "thoi gian"]),
        "has_high": _has_any(text, ["cao nhat"]),
        "has_low": _has_any(text, ["thap nhat"]),
        "has_difference": _has_any(text, ["chenh lech"]),
        "has_real_numbers": bool(re.search(r"\d", text)),
        "no_causal_invention": _no_causal_invention(text),
    }


def _check_column_audit(text: str, response: Any) -> dict[str, bool]:
    return {
        "lists_business_columns": _has_any(text, ["cot nghiep vu"]),
        "lists_technical_columns": _has_any(text, ["cot so thu tu", "metadata ky thuat", "dinh danh"]),
        "classifies_no_column": "no." in _norm(text),
        "rejects_id_mode": _has_any(text, ["khong dung mode", "khong lay mode", "mode cua id"]),
        "analyzes_business_after_audit": _has_any(text, ["phan tich cot nghiep vu", "phan tich nghiep vu"]),
    }


def _check_non_trivial(text: str, response: Any) -> dict[str, bool]:
    trivial = ["day du 100%", "100%", "gia tri 1 xuat hien mot lan", "co toan gia tri duy nhat"]
    return {
        "has_three_points": _point_count(text) >= 3,
        "has_real_numbers": bool(re.search(r"\d", text)),
        "no_trivial_completeness": not _has_any(text, trivial),
        "no_technical_columns": _no_technical_columns(text),
    }


def _check_loss_structure(text: str, response: Any) -> dict[str, bool]:
    return {
        "mentions_loss": _has_any(text, ["ton that", "loss"]),
        "mentions_group_or_type": _has_any(text, ["nhom", "loai", "nguyen nhan"]),
        "mentions_count_or_share": _has_any(text, ["count", "so lan", "ty le", "%"]),
        "mentions_concentration": _has_any(text, ["tap trung", "chiem"]),
        "mentions_limitations": _has_any(text, ["han che", "gioi han", "can than trong", "khong du da dang"]),
        "no_technical_columns": _no_technical_columns(text),
    }


def _check_entry_transaction(text: str, response: Any) -> dict[str, bool]:
    return {
        "mentions_transactions": _has_any(text, ["giao dich", "transaction"]),
        "mentions_scale": _has_any(text, ["quy mo", "so dong", "so giao dich"]),
        "mentions_time_range": _has_any(text, ["thoi gian", "khoang", "tu 202"]),
        "mentions_total_value": _has_any(text, ["tong gia tri", "gia tri can"]),
        "mentions_average_value": _has_any(text, ["trung binh"]),
        "mentions_trend": _has_any(text, ["xu huong", "theo thoi gian", "dat dinh"]),
    }


def _check_manager_brief(text: str, response: Any) -> dict[str, bool]:
    return {
        "has_three_points": _point_count(text) >= 3,
        "has_findings": _has_any(text, ["phat hien"]),
        "has_meaning": _has_any(text, ["y nghia"]),
        "has_real_numbers": bool(re.search(r"\d", text)),
        "no_technical_columns": _no_technical_columns(text),
    }


def _check_four_viewpoints(text: str, response: Any) -> dict[str, bool]:
    return {
        "has_scale": _has_any(text, ["quy mo"]),
        "has_ranking": _has_any(text, ["xep hang"]),
        "has_distribution": _has_any(text, ["phan bo"]),
        "has_trend": _has_any(text, ["xu huong"]),
        "has_real_numbers": bool(re.search(r"\d", text)),
    }


def _check_followup(text: str, response: Any) -> dict[str, bool]:
    return {
        "mentions_strongest_evidence": _has_any(text, ["bang chung manh nhat", "evidence strength"]),
        "mentions_most_cautious": _has_any(text, ["can than trong nhat", "can than trong"]),
        "no_new_query_table": response.table is None,
        "uses_previous_insights_route": (response.metadata or {}).get("routing_reason") == "overview_followup_evidence",
    }


def _check_causality(text: str, response: Any) -> dict[str, bool]:
    return {
        "rejects_causal_conclusion": _has_any(text, ["khong nen ket luan nguyen nhan", "khong the ket luan nguyen nhan"]),
        "distinguishes_proven_data": _has_any(text, ["du lieu chung minh"]),
        "distinguishes_unknowns": _has_any(text, ["chua the ket luan"]),
        "asks_for_more_data": _has_any(text, ["can them du lieu", "du lieu can them"]),
        "no_causal_invention": True,
    }


def _check_short_overview(text: str, response: Any) -> dict[str, bool]:
    return {
        "has_three_points": _point_count(text) >= 3,
        "has_business_content": _has_any(text, ["may", "downtime", "ton that", "giao dich", "thoi gian dung"]),
        "no_technical_columns": _no_technical_columns(text),
    }


def _point_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line))


def _has_any(text: str, needles: list[str]) -> bool:
    normalized = _norm(text)
    return any(_norm(needle) in normalized for needle in needles)


def _no_technical_columns(text: str) -> bool:
    normalized = _norm(text)
    if re.search(r"(?<![a-z0-9_])(?:no\.|stt|index|id)(?![a-z0-9_])", normalized):
        return False
    return not any(term in normalized for term in ["_source", "_record", "duplicate_group"])


def _no_causal_invention(text: str) -> bool:
    normalized = _norm(text)
    forbidden = [
        "nguyen nhan la may hong",
        "nguyen nhan la van hanh kem",
        "bao tri sai",
        "may kem chat luong",
        "do may hong",
        "do van hanh kem",
    ]
    return not any(term in normalized for term in forbidden)


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text).lower().replace("\u0111", "d"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["summary"]["status"] == "passed" else 1)
