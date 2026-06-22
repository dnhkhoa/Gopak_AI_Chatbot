from __future__ import annotations

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_operation(question: str) -> DetectionResult:
    q = normalize_text(question)
    if any(term in q for term in ["dashboard", "tong quan"]):
        return DetectionResult("dashboard", 0.95, ["dashboard/tong quan"])
    if any(term in q for term in ["bao cao", "report", "html", "excel", "xuat ket qua", "xuat bao cao"]):
        return DetectionResult("report", 0.93, ["report/export keyword"])
    if any(term in q for term in ["ve", "bieu do", "chart", "plot"]):
        return DetectionResult("chart", 0.92, ["chart keyword"])
    return DetectionResult("query", 0.85, ["default analytical query"])
