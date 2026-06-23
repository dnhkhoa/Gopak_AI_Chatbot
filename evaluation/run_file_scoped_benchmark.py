from __future__ import annotations

import csv
import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files

CASES_PATH = ROOT / "evaluation" / "file_scoped_benchmark_cases.json"
ARTIFACTS = ROOT / "artifacts"


FILE_KEYS = {
    "entry": "EntryTransaction",
    "loss": "Loss_Assignment",
    "machine": "Machine_Downtime",
}


def _records_by_key() -> dict[str, dict[str, Any]]:
    records = list_uploaded_files()
    mapped: dict[str, dict[str, Any]] = {}
    for key, needle in FILE_KEYS.items():
        mapped[key] = next((record for record in records if needle.lower() in str(record.get("filename", "")).lower()), {})
    return mapped


def generate_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def add(category: str, question: str, file_key: str | None, expected_type: str, *, no_sql: bool = False, split: str | None = None, sequence: str | None = None) -> None:
        idx = len(cases) + 1
        cases.append(
            {
                "id": f"FSB-{idx:03d}",
                "split": split or ("dev" if idx <= 140 else "holdout"),
                "category": category,
                "question": question,
                "active_file_key": file_key,
                "expected_response_type": expected_type,
                "expected_no_sql": no_sql,
                "sequence_id": sequence,
            }
        )

    deterministic = [
        ("Top 5 may theo tong downtime", "machine", "table"),
        ("Tong downtime la bao nhieu", "machine", "scalar"),
        ("Dem so dong downtime", "machine", "scalar"),
        ("Ve bieu do cot top 5 may theo downtime", "machine", "chart"),
        ("Top 5 nguyen nhan ton that", "loss", "table"),
        ("Tong thoi luong ton that", "loss", "scalar"),
        ("Theo nhom ton that dem so lan", "loss", "table"),
        ("Tong gia tri can la bao nhieu", "entry", "scalar"),
        ("Co bao nhieu cong khac nhau", "entry", "scalar"),
    ]
    for i in range(45):
        question, file_key, expected = deterministic[i % len(deterministic)]
        add("deterministic", f"{question} #{i + 1}", file_key, expected)

    llm_like = [
        ("Hay phan tich bat thuong va neu bang tom tat ngan gon", "machine"),
        ("So sanh may co downtime cao voi may con lai", "machine"),
        ("Tao nhan xet cho 3 nhom ton that quan trong nhat", "loss"),
        ("Cho toi mot insight ngan ve luong xe ra vao cong", "entry"),
    ]
    for i in range(30):
        q, file_key = llm_like[i % len(llm_like)]
        add("real_llm_candidate", f"{q} #{i + 1}", file_key, "table")

    for i in range(20):
        add("clarification", f"Cau nay mo ho ve hieu suat #{i + 1}", "machine", "clarification", no_sql=True)

    refusal_questions = [
        "Du bao downtime ngay mai",
        "Gia co phieu cua cong ty la bao nhieu",
        "Viet email cho khach hang",
        "Noi dung cua Loss_Assignment khi dang chon file khac",
    ]
    for i in range(20):
        file_key = "machine" if i % 4 == 3 else "entry"
        add("refusal", f"{refusal_questions[i % len(refusal_questions)]} #{i + 1}", file_key, "refusal", no_sql=True)

    for i in range(10):
        add("safe_failure", f"Truy van khong an toan bang SQL delete #{i + 1}", "machine", "refusal", no_sql=True)

    file_scope = [
        ("noi dung cua data", "machine", "data_overview"),
        ("cho toi xem schema", "loss", "schema"),
        ("xem 5 dong mau", "entry", "sample_table"),
        ("du lieu tu ngay nao", "machine", "data_overview"),
        ("chat luong du lieu", "loss", "data_quality"),
    ]
    for i in range(30):
        q, file_key, expected = file_scope[i % len(file_scope)]
        add("file_scope", f"{q} #{i + 1}", file_key, expected, no_sql=True)

    multipart = [
        "Top 5 may, chi thang gan nhat, ve bieu do cot",
        "Top 10 nguyen nhan, gom theo nhom, sap xep giam dan",
        "Tong downtime va so lan dung theo may",
        "Bao cao HTML top downtime va bang chi tiet",
        "So sanh theo thang va ve line chart",
    ]
    for i in range(35):
        add("multipart", f"{multipart[i % len(multipart)]} #{i + 1}", "machine" if i % 2 == 0 else "loss", "table")

    for seq in range(15):
        sequence_id = f"CTX-{seq + 1:02d}"
        file_key = "machine" if seq % 2 == 0 else "loss"
        turns = [
            "Top 5 may theo tong downtime" if file_key == "machine" else "Top 5 nguyen nhan ton that",
            "Chi lay thang gan nhat",
            "Ve bieu do cot",
            "Quay lai cau dau tien",
            "Doi thanh top 3",
            "Xem schema",
        ]
        for turn in turns:
            expected = "schema" if turn.lower() == "xem schema" else "table"
            add("context_sequence", turn, file_key, expected, no_sql=expected == "schema", sequence=sequence_id)

    for seq in range(10):
        sequence_id = f"XFILE-{seq + 1:02d}"
        add("cross_file_sequence", "noi dung cua data", "machine", "data_overview", no_sql=True, sequence=sequence_id)
        add("cross_file_sequence", "hoi ve Loss_Assignment", "machine", "refusal", no_sql=True, sequence=sequence_id)
        add("cross_file_sequence", "Top 5 nguyen nhan ton that", "loss", "table", sequence=sequence_id)
        add("cross_file_sequence", "hoi ve Machine_Downtime", "loss", "refusal", no_sql=True, sequence=sequence_id)

    for i, case in enumerate(cases):
        case["split"] = "dev" if i < 140 else "holdout"
    return cases


def _response_matches(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if expected == "error" and actual == "error":
        return True
    if expected == "table" and actual in {"table", "chart", "dashboard", "report", "scalar"}:
        return True
    if expected == "scalar" and actual in {"scalar", "table"}:
        return True
    if expected == "refusal" and actual in {"refusal", "clarification"}:
        return True
    return False


def run() -> dict[str, Any]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cases = generate_cases()
    CASES_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    records = _records_by_key()
    settings = get_settings()

    results = []
    traces: dict[str, list[dict[str, Any]]] = defaultdict(list)
    file_switch_traces: dict[str, list[dict[str, Any]]] = defaultdict(list)

    with tempfile.TemporaryDirectory(prefix="gopak-file-scoped-benchmark-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        active_conversations: dict[str, str] = {}
        for case in cases:
            sequence_id = case.get("sequence_id") or case["id"]
            conversation_id = active_conversations.get(sequence_id)
            if not conversation_id:
                conversation_id = app.create_conversation(title=sequence_id).id
                active_conversations[sequence_id] = conversation_id
            expected_file_key = case.get("active_file_key")
            if expected_file_key:
                record = records.get(expected_file_key) or {}
                if record.get("id"):
                    app.set_active_file(conversation_id, str(record["id"]))
            start = perf_counter()
            response = app.process_message(conversation_id, case["question"], debug=True)
            latency_ms = round((perf_counter() - start) * 1000, 1)
            metadata = response.metadata or {}
            debug = metadata.get("debug") if isinstance(metadata.get("debug"), dict) else {}
            sql = metadata.get("generated_sql") or (debug or {}).get("sql")
            expected_record = records.get(expected_file_key or "") or {}
            expected_file_id = expected_record.get("id")
            file_ok = not expected_file_id or metadata.get("active_file_id") == expected_file_id
            no_sql_ok = not case["expected_no_sql"] or not sql
            type_ok = _response_matches(response.response_type, case["expected_response_type"])
            passed = bool(type_ok and no_sql_ok and file_ok)
            item = {
                **case,
                "actual_response_type": response.response_type,
                "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
                "active_file_id": metadata.get("active_file_id"),
                "active_file_name": metadata.get("active_file_name"),
                "file_scope_validated": metadata.get("file_scope_validated"),
                "sql_present": bool(sql),
                "latency_ms": latency_ms,
                "passed": passed,
            }
            results.append(item)
            if case.get("sequence_id"):
                traces[case["sequence_id"]].append(item)
            if case["category"] == "cross_file_sequence":
                file_switch_traces[case["sequence_id"]].append(item)

    by_split = {split: [item for item in results if item["split"] == split] for split in ["dev", "holdout"]}
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
        "dev": _metrics(by_split["dev"]),
        "holdout": _metrics(by_split["holdout"]),
        "by_category": {category: _metrics([item for item in results if item["category"] == category]) for category in sorted({item["category"] for item in results})},
        "p50_latency_ms": median([item["latency_ms"] for item in results]) if results else 0,
    }

    (ARTIFACTS / "file_scoped_benchmark_dev.json").write_text(json.dumps(by_split["dev"], ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "file_scoped_benchmark_holdout.json").write_text(json.dumps(by_split["holdout"], ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "routing_metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "multipart_coverage.json").write_text(json.dumps(_metrics([item for item in results if item["category"] == "multipart"]), indent=2), encoding="utf-8")
    (ARTIFACTS / "context_switch_traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "file_switch_traces.json").write_text(json.dumps(file_switch_traces, ensure_ascii=False, indent=2), encoding="utf-8")
    violations = [item for item in results if not item["passed"] or item.get("file_scope_validated") is False and item["expected_response_type"] not in {"clarification", "refusal", "error"}]
    (ARTIFACTS / "file_scope_violations.json").write_text(json.dumps(violations, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_confusion(results)
    _write_latency(results)
    _write_failures(results)
    _write_summary(summary)
    pd.DataFrame(cases).to_excel(ARTIFACTS / "customer_benchmark_questions.xlsx", index=False)
    return summary


def _metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(items),
        "passed": sum(1 for item in items if item["passed"]),
        "accuracy": round(sum(1 for item in items if item["passed"]) / max(1, len(items)), 4),
    }


def _write_confusion(results: list[dict[str, Any]]) -> None:
    rows = Counter((item["expected_response_type"], str(item.get("actual_response_type"))) for item in results)
    with (ARTIFACTS / "routing_confusion_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["expected", "actual", "count"])
        for (expected, actual), count in sorted(rows.items()):
            writer.writerow([expected, actual, count])


def _write_latency(results: list[dict[str, Any]]) -> None:
    with (ARTIFACTS / "benchmark_latency.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "split", "category", "latency_ms", "execution_mode"])
        writer.writeheader()
        for item in results:
            writer.writerow({key: item.get(key) for key in writer.fieldnames})


def _write_failures(results: list[dict[str, Any]]) -> None:
    failed = [item for item in results if not item["passed"]]
    lines = ["# Benchmark Failures", "", f"Failed: {len(failed)} / {len(results)}", ""]
    for item in failed[:80]:
        lines.append(f"- {item['id']} [{item['category']}]: expected {item['expected_response_type']}, got {item['actual_response_type']}; file={item.get('active_file_name')}; sql={item.get('sql_present')}")
    (ARTIFACTS / "benchmark_failures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary(summary: dict[str, Any]) -> None:
    lines = [
        "# File-Scoped Benchmark Summary",
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Accuracy: {summary['accuracy']:.2%}",
        f"- Dev accuracy: {summary['dev']['accuracy']:.2%}",
        f"- Holdout accuracy: {summary['holdout']['accuracy']:.2%}",
        f"- P50 latency: {summary['p50_latency_ms']} ms",
        "",
        "## Category Metrics",
        "",
        "| Category | Total | Passed | Accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, metrics in summary["by_category"].items():
        lines.append(f"| {category} | {metrics['total']} | {metrics['passed']} | {metrics['accuracy']:.2%} |")
    (ARTIFACTS / "benchmark_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=True, indent=2))
