from __future__ import annotations

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_operation(question: str) -> DetectionResult:
    q = normalize_text(question)
    if any(term in q for term in ["bao cao", "report", "html", "excel", "xuat ket qua", "xuat bao cao"]):
        return DetectionResult("report", 0.93, ["report/export keyword"])
    if any(term in q for term in ["dashboard", "tong quan"]):
        return DetectionResult("dashboard", 0.95, ["dashboard/tong quan"])
    if any(term in q for term in ["bieu do", "chart", "plot", "ve cot", "ve line", "ve chart", "ve bieu do"]) and not _negates_chart(q):
        return DetectionResult("chart", 0.92, ["chart keyword"])
    return DetectionResult("query", 0.85, ["default analytical query"])


def _negates_chart(q: str) -> bool:
    return any(term in q for term in ["bo bieu do", "bo chart", "khong ve bieu do", "khong ve chart", "khong can bieu do", "khong can chart"])
