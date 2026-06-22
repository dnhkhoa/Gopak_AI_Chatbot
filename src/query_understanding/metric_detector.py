from __future__ import annotations

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_metric(question: str, duration_col: str | None, machine_col: str | None, loss_name_col: str | None) -> DetectionResult:
    q = normalize_text(question)
    if any(term in q for term in ["so may khac nhau", "bao nhieu may khac nhau"]):
        return DetectionResult({"aggregation": "count_distinct", "column": machine_col, "name": "machine_count"}, 0.96, ["distinct machine"])
    if any(term in q for term in ["nguyen nhan khac nhau", "so nguyen nhan"]) or ("nguyen nhan" in q and "khac nhau" in q):
        return DetectionResult({"aggregation": "count_distinct", "column": loss_name_col, "name": "reason_count"}, 0.96, ["distinct reason"])
    if any(term in q for term in ["so ban ghi", "bao nhieu dong", "tong so ban ghi", "count"]):
        return DetectionResult({"aggregation": "count", "column": None, "name": "row_count"}, 0.96, ["record count"])
    if any(term in q for term in ["trung binh", "average", "avg"]):
        return DetectionResult({"aggregation": "avg", "column": duration_col, "name": "avg_duration_seconds"}, 0.94, ["average duration"])
    if any(term in q for term in ["median", "trung vi"]):
        return DetectionResult({"aggregation": "median", "column": duration_col, "name": "median_duration_seconds"}, 0.92, ["median duration"])
    if any(term in q for term in ["nho nhat", "min"]) and not any(term in q for term in ["may", "nguyen nhan", "nhom", "bottom"]):
        return DetectionResult({"aggregation": "min", "column": duration_col, "name": "min_duration_seconds"}, 0.92, ["minimum duration"])
    if any(term in q for term in ["lon nhat", "max", "lau nhat"]) and not any(term in q for term in ["may", "nguyen nhan", "nhom", "top"]):
        return DetectionResult({"aggregation": "max", "column": duration_col, "name": "max_duration_seconds"}, 0.92, ["maximum duration"])
    if any(term in q for term in ["bao nhieu gio", "chiem bao nhieu gio"]):
        return DetectionResult({"aggregation": "sum", "column": duration_col, "name": "total_duration_seconds"}, 0.92, ["sum duration in hours"])
    if any(term in q for term in ["dem", "so lan", "bao nhieu lan", "lan dung", "lan downtime", "cac lan dung", "nhung lan dung", "xuat hien"]):
        return DetectionResult({"aggregation": "count", "column": None, "name": "row_count"}, 0.93, ["event count"])
    if any(term in q for term in ["downtime", "thoi gian", "thoi luong", "dung", "ngung", "dt", "tong", "bao lau", "bao nhieu gio"]):
        return DetectionResult({"aggregation": "sum", "column": duration_col, "name": "total_duration_seconds"}, 0.90, ["sum duration"])
    return DetectionResult(None, 0.0, unresolved_terms=["metric"])
