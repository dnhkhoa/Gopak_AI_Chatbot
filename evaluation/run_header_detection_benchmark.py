from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from time import perf_counter

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingestion.workbook_scanner import load_workbook_tables


ARTIFACTS = ROOT / "artifacts"


HEADERS = ["No.", "Máy", "Thời gian bắt đầu", "Thời gian kết thúc", "Thời lượng", "Tên tổn thất", "Nhóm tổn thất", "Loại tổn thất", "Note"]
ROW = [1, "Máy 8", "12/12/2025 10:14:00", "12/12/2025 10:14:16", "00:00:15", "SETUP MÁY", "Sản xuất", "Dừng vận hành", None]


def _write_case(path: Path, header_row: int, start_col: int, *, metadata: bool = False, repeated: bool = False, footer: bool = False, garbage: bool = False, sheets: int = 1) -> None:
    wb = Workbook()
    for sheet_idx in range(sheets):
        ws = wb.active if sheet_idx == 0 else wb.create_sheet(f"Sheet{sheet_idx + 1}")
        ws.title = "Report" if sheet_idx == 0 else f"Other{sheet_idx + 1}"
        if metadata:
            ws.cell(4, start_col, "Operation Downtime")
            ws.cell(6, start_col, "From time:")
            ws.cell(6, start_col + 1, "12/09/2025 10:18")
            ws.cell(7, start_col, "To time:")
            ws.cell(7, start_col + 1, "12/12/2025 10:18")
        for offset, header in enumerate(HEADERS):
            ws.cell(header_row, start_col + offset, header)
        if garbage:
            ws.cell(header_row, start_col + len(HEADERS), "8")
            ws.cell(header_row + 1, start_col + len(HEADERS), None)
        for idx in range(1, 6):
            values = ROW.copy()
            values[0] = idx
            for offset, value in enumerate(values):
                ws.cell(header_row + idx, start_col + offset, value)
        if repeated:
            for offset, header in enumerate(HEADERS):
                ws.cell(header_row + 3, start_col + offset, header)
        if footer:
            ws.cell(header_row + 8, start_col, "Total")
            ws.cell(header_row + 8, start_col + 1, 5)
    wb.save(path)


def _cases(tmp: Path) -> list[dict]:
    specs = [
        ("header_row_1", 1, 1, {}),
        ("header_row_10", 10, 1, {}),
        ("header_row_35", 35, 4, {"metadata": True, "garbage": True}),
        ("metadata_above", 20, 3, {"metadata": True}),
        ("leading_empty_columns", 12, 5, {}),
        ("trailing_garbage", 15, 2, {"garbage": True}),
        ("repeated_header", 18, 2, {"repeated": True}),
        ("footer_total", 22, 2, {"footer": True}),
        ("multiple_sheets", 10, 2, {"sheets": 2}),
        ("merged_title_like", 30, 4, {"metadata": True}),
        ("vietnamese_english", 8, 1, {}),
        ("header_more_columns", 16, 3, {"garbage": True}),
        ("non_sequential_no", 25, 4, {"metadata": True}),
        ("metadata_header_like", 28, 4, {"metadata": True}),
        ("sample_shape", 35, 4, {"metadata": True, "garbage": True, "footer": True}),
    ]
    cases = []
    for name, header_row, start_col, kwargs in specs:
        path = tmp / f"{name}.xlsx"
        _write_case(path, header_row, start_col, **kwargs)
        cases.append({"id": name, "path": str(path), "expected_header_row": header_row, "expected_first_column": _col(start_col), "expected_last_column": _col(start_col + len(HEADERS) - 1)})
    return cases


def _col(index: int) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(index)


def run() -> dict:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = []
    started = perf_counter()
    with tempfile.TemporaryDirectory() as temp:
        for case in _cases(Path(temp)):
            tables = load_workbook_tables(Path(case["path"]))
            profile = tables[0].profile if tables else None
            passed = bool(
                profile
                and profile.header_row == case["expected_header_row"]
                and profile.first_column == case["expected_first_column"]
                and profile.last_column == case["expected_last_column"]
            )
            results.append(
                {
                    **{k: v for k, v in case.items() if k != "path"},
                    "actual_header_row": profile.header_row if profile else None,
                    "actual_first_column": profile.first_column if profile else None,
                    "actual_last_column": profile.last_column if profile else None,
                    "confidence": profile.header_confidence if profile else 0,
                    "row_count": profile.row_count if profile else 0,
                    "passed": passed,
                    "failure_type": None if passed else "HEADER_ROW_ERROR",
                }
            )
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
        "latency_ms": round((perf_counter() - started) * 1000, 1),
    }
    (ARTIFACTS / "header_detection_results.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [item for item in results if not item["passed"]]
    lines = ["# Header Detection Failures", "", f"Failed: {len(failures)} / {len(results)}", ""]
    for item in failures:
        lines.append(f"- {item['id']}: expected row {item['expected_header_row']} {item['expected_first_column']}:{item['expected_last_column']}, got {item['actual_header_row']} {item['actual_first_column']}:{item['actual_last_column']}")
    (ARTIFACTS / "header_detection_failures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=True, indent=2))
