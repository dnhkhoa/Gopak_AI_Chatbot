from __future__ import annotations

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_output(question: str) -> DetectionResult:
    q = normalize_text(question)
    if any(term in q for term in ["dashboard", "tong quan"]):
        return DetectionResult("dashboard", 0.95, ["dashboard"])
    if any(term in q for term in ["bao cao", "report", "html", "excel", "xuat ket qua", "xuat bao cao"]):
        return DetectionResult("report", 0.93, ["report/export"])
    if any(term in q for term in ["line", "theo ngay", "theo tuan", "theo thang"]) and any(term in q for term in ["ve", "bieu do", "chart"]):
        return DetectionResult("line", 0.90, ["time chart"])
    if any(term in q for term in ["pie", "tron", "ty trong"]):
        return DetectionResult("pie", 0.90, ["pie"])
    if any(term in q for term in ["ve", "bieu do", "chart", "bar"]):
        return DetectionResult("bar", 0.90, ["chart"])
    if any(term in q for term in ["bao nhieu", "tong", "dem", "trung binh", "lon nhat", "nho nhat"]) and "top" not in q:
        return DetectionResult("text", 0.85, ["scalar phrasing"])
    return DetectionResult("table", 0.80, ["default table"])
