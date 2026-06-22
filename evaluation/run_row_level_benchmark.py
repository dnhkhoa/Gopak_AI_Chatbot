from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application import ChatApplicationService
from src.files.upload_store import list_uploaded_files


ARTIFACTS = ROOT / "artifacts"
OPERATION_SAMPLE = "Operation_Downtime_20251212_101824 (2)(1).xlsx"
FALLBACK_SAMPLE = "Machine_Downtime_20260203_100753.xlsx"


def _active_record() -> tuple[dict[str, Any], bool]:
    records = list_uploaded_files()
    operation = next((item for item in records if item.get("filename") == OPERATION_SAMPLE), None)
    if operation:
        return operation, True
    fallback = next((item for item in records if item.get("filename") == FALLBACK_SAMPLE), None)
    if fallback:
        return fallback, False
    raise RuntimeError("No uploaded downtime workbook found for row-level benchmark.")


def _table_for_record(catalog: dict, filename: str) -> dict:
    return next(table for table in catalog.get("tables", []) if filename in str(table.get("source", "")))


def _cases(df: pd.DataFrame, sample_available: bool) -> list[dict[str, Any]]:
    first = df.iloc[0]
    last = df.iloc[-1]
    machines = [str(v) for v in df["may"].dropna().unique()[:5]] if "may" in df.columns else []
    machine = "Máy 8" if sample_available and "Máy 8" in set(df["may"].dropna()) else (machines[0] if machines else "")
    date_value = pd.Timestamp(first["thoi_gian_bat_dau"]).strftime("%d/%m/%Y")
    cases: list[dict[str, Any]] = []

    def add(category: str, question: str, expected_type: str, expected_records: list[int] | None = None, no_sql: bool = False) -> None:
        cases.append(
            {
                "id": f"ROW-{len(cases) + 1:03d}",
                "category": category,
                "question": question,
                "expected_intent": expected_type,
                "expected_records": expected_records or [],
                "expected_source_rows": [int(df.loc[df["_record_no"].isin(expected_records or []), "_source_excel_row"].iloc[0])] if expected_records and len(expected_records) == 1 else [],
                "expected_fields": {},
                "interval_mode": "",
                "duration_policy": "reported_duration_seconds",
                "expected_no_sql": no_sql,
            }
        )

    for q in ["No 1 la gi?", "Cho toi ban ghi so 1.", "Dong co No bang 1.", "Show record number 1."]:
        add("record_number", q, "record_detail", [1])
    for no in [2, 3, int(first["_record_no"]), int(last["_record_no"])]:
        add("record_number", f"Record {no}.", "record_detail", [no])
    add("record_number", "Cac record tu No 10 den No 20.", "record_table", list(range(10, 21)))
    for no in [5, 10, 20]:
        add("record_number", f"No {no} la gi?", "record_detail", [no])

    add("source_row", f"Hang Excel {int(first['_source_excel_row'])} chua gi?", "record_detail", [int(first["_record_no"])])
    add("source_row", "Ban ghi dau tien sau header.", "record_detail", [int(first["_record_no"])])
    for idx in [2, 10, 100, 500, 1000, min(2000, len(df)), len(df)]:
        expected = int(df.loc[df["_data_row_index"] == idx, "_record_no"].iloc[0])
        add("source_row", f"Dong du lieu thu {idx}.", "record_detail", [expected])

    for i in range(15):
        add("machine_date", f"{machine} ngay {date_value} dung luc nao? #{i+1}", "timeline")
    for i in range(12):
        add("time_window", f"{machine} co dung tu 8h den 9h ngay {date_value} khong? #{i+1}", "timeline")
    for i in range(10):
        add("first_latest", f"Ban ghi gan nhat cua {machine}. #{i+1}", "record_detail")
    for i in range(8):
        add("cross_midnight", f"Cac event overlap 00:00 ngay {date_value}. #{i+1}", "timeline")
    for i in range(10):
        question = ["Co record trung khong?", "Dong nao thieu loss name?", "Duration nao dai hon 24 gio?", "Co start time lon hon end time khong?"][i % 4]
        add("data_quality", f"{question} #{i+1}", "record_table")
    for i in range(5):
        add("operating_time", f"{machine} hoat dong luc nao ngay {date_value}? #{i+1}", "clarification", no_sql=True)
    return cases[:82]


def run() -> dict[str, Any]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    app = ChatApplicationService()
    catalog = app.get_catalog(force=True)
    record, sample_available = _active_record()
    table = _table_for_record(catalog, str(record["filename"]))
    df = pd.read_parquet(table["parquet_path"])
    conv = app.create_conversation(title="Row-level benchmark")
    app.set_active_file(conv.id, str(record["id"]))
    results = []
    for case in _cases(df, sample_available):
        start = perf_counter()
        response = app.process_message(conv.id, case["question"], debug=True)
        latency = round((perf_counter() - start) * 1000, 1)
        rows = response.table.rows if response.table else []
        actual_records = []
        actual_source_rows = []
        for row in rows:
            if row.get("_record_no") is not None:
                actual_records.append(int(row["_record_no"]))
            if row.get("_source_excel_row") is not None:
                actual_source_rows.append(int(row["_source_excel_row"]))
        type_ok = response.response_type == case["expected_intent"] or (case["expected_intent"] == "record_table" and response.table is not None)
        record_ok = not case["expected_records"] or set(case["expected_records"]).issubset(set(actual_records))
        no_sql_ok = not case["expected_no_sql"] or not ((response.metadata.get("debug") or {}).get("sql") or response.metadata.get("generated_sql"))
        passed = bool(type_ok and record_ok and no_sql_ok)
        results.append(
            {
                **case,
                "active_file_id": record["id"],
                "actual_intent": response.metadata.get("execution_mode") or response.response_type,
                "actual_response_type": response.response_type,
                "actual_records": actual_records,
                "actual_source_rows": actual_source_rows,
                "actual_fields": rows[0] if rows else {},
                "passed": passed,
                "failure_type": None if passed else _failure_type(case, response, actual_records),
                "latency_ms": latency,
                "notes": "" if sample_available else f"Sample file {OPERATION_SAMPLE} was not available; used {record['filename']} fallback.",
            }
        )
    latencies = [item["latency_ms"] for item in results]
    summary = {
        "sample_file_available": sample_available,
        "active_file_name": record["filename"],
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
        "p50_latency_ms": median(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0,
    }
    (ARTIFACTS / "row_level_benchmark_results.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _write_failures(results)
    _write_checks(df, summary)
    _write_latency(results)
    return summary


def _failure_type(case: dict, response, actual_records: list[int]) -> str:
    if response.metadata.get("active_file_id") is None:
        return "FILE_SCOPE_VIOLATION"
    if case["expected_records"] and not set(case["expected_records"]).issubset(set(actual_records)):
        return "RECORD_NO_ERROR"
    if case["expected_intent"] == "clarification" and response.response_type != "clarification":
        return "OPERATING_TIME_HALLUCINATION"
    return "INCOMPLETE_RECORD_RESPONSE"


def _write_failures(results: list[dict[str, Any]]) -> None:
    failures = [item for item in results if not item["passed"]]
    lines = ["# Row-Level Benchmark Failures", "", f"Failed: {len(failures)} / {len(results)}", ""]
    for item in failures[:80]:
        lines.append(f"- {item['id']} [{item['category']}]: expected {item['expected_intent']} records={item['expected_records']}, got {item['actual_response_type']} records={item['actual_records']} failure={item['failure_type']}")
    (ARTIFACTS / "row_level_benchmark_failures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_checks(df: pd.DataFrame, summary: dict[str, Any]) -> None:
    provenance = {
        "active_file_name": summary["active_file_name"],
        "row_count": int(len(df)),
        "first_record": df.head(1).to_dict(orient="records"),
        "last_record": df.tail(1).to_dict(orient="records"),
        "source_excel_row_min": int(df["_source_excel_row"].min()),
        "source_excel_row_max": int(df["_source_excel_row"].max()),
    }
    intervals = {
        "cross_midnight_records": int((df["thoi_gian_bat_dau"].dt.date != df["thoi_gian_ket_thuc"].dt.date).sum()) if {"thoi_gian_bat_dau", "thoi_gian_ket_thuc"}.issubset(df.columns) else 0,
        "negative_intervals": int(((df["thoi_gian_ket_thuc"] - df["thoi_gian_bat_dau"]).dt.total_seconds() < 0).sum()) if {"thoi_gian_bat_dau", "thoi_gian_ket_thuc"}.issubset(df.columns) else 0,
    }
    duration = {
        "reported_parse_non_null": int(df["duration_reported_seconds"].notna().sum()) if "duration_reported_seconds" in df.columns else 0,
        "calculated_parse_non_null": int(df["duration_calculated_seconds"].notna().sum()) if "duration_calculated_seconds" in df.columns else 0,
        "duration_anomalies": int(df["duration_anomaly"].sum()) if "duration_anomaly" in df.columns else 0,
        "policy": "duration_seconds = duration_reported_seconds when valid",
    }
    duplicate = {
        "exact_duplicate_records": int(df["_is_exact_duplicate"].sum()) if "_is_exact_duplicate" in df.columns else 0,
        "duplicate_groups": int(df["_duplicate_group_id"].dropna().nunique()) if "_duplicate_group_id" in df.columns else 0,
        "overlap_records": int(df["_overlaps_same_machine"].sum()) if "_overlaps_same_machine" in df.columns else 0,
    }
    (ARTIFACTS / "record_provenance_checks.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "interval_query_checks.json").write_text(json.dumps(intervals, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "duration_reconciliation.json").write_text(json.dumps(duration, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "duplicate_and_overlap_report.json").write_text(json.dumps(duplicate, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_latency(results: list[dict[str, Any]]) -> None:
    with (ARTIFACTS / "row_query_latency.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "category", "latency_ms", "actual_intent", "passed"])
        writer.writeheader()
        for item in results:
            writer.writerow({key: item.get(key) for key in writer.fieldnames})


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=True, indent=2))
