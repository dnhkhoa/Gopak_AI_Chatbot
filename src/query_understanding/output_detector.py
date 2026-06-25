from __future__ import annotations

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_output(question: str) -> DetectionResult:
    q = normalize_text(question)
    if any(term in q for term in ["bao cao", "report", "html", "excel", "xuat ket qua", "xuat bao cao"]):
        return DetectionResult("report", 0.93, ["report/export"])
    if any(term in q for term in ["dashboard", "tong quan"]):
        return DetectionResult("dashboard", 0.95, ["dashboard"])
    chart_requested = any(term in q for term in ["bieu do", "chart", "plot", "bar", "ve cot", "ve line", "ve chart", "ve bieu do"]) and not _negates_chart(q)
    if any(term in q for term in ["line", "theo ngay", "theo tuan", "theo thang", "xu huong", "qua thoi gian", "theo thoi gian"]) and chart_requested:
        return DetectionResult("line", 0.90, ["time chart"])
    if chart_requested and ("top" in q or any(term in q for term in ["cao nhat", "nhieu nhat", "pho bien nhat"])):
        return DetectionResult("bar", 0.90, ["ranked chart"])
    if chart_requested and any(term in q for term in ["pie", "tron", "ty trong", "phan bo", "ty le"]):
        return DetectionResult("pie", 0.90, ["pie"])
    if chart_requested:
        return DetectionResult("bar", 0.90, ["chart"])
    if any(term in q for term in ["bao nhieu", "tong", "dem", "trung binh", "lon nhat", "nho nhat"]) and "top" not in q:
        return DetectionResult("text", 0.85, ["scalar phrasing"])
    return DetectionResult("table", 0.80, ["default table"])


def _negates_chart(q: str) -> bool:
    return any(term in q for term in ["bo bieu do", "bo chart", "khong ve bieu do", "khong ve chart", "khong can bieu do", "khong can chart"])
