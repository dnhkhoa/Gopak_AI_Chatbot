from __future__ import annotations

from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def detect_dimension(question: str, machine_col: str | None, loss_name_col: str | None, loss_group_col: str | None, start_time_col: str | None) -> DetectionResult:
    q = normalize_text(question)
    dims = []
    evidence = []
    if any(term in q for term in ["theo thang", "theo th?ng", "tung thang", "t?ng th?ng", "moi thang", "giua cac thang", "theo ngay", "theo tuan", "by month", "by day", "by week", "per month", "per day", "daily", "monthly"]):
        if start_time_col:
            dims.append(start_time_col)
            evidence.append("time grouping")
    skip_machine_dimension = any(term in q for term in ["chinh may", "setup may"]) and any(
        term in q for term in ["loi", "nguyen nhan", "ton that", "lien quan"]
    )
    if any(term in q for term in ["may", "m?y", "machine"]) and not skip_machine_dimension:
        if machine_col:
            dims.append(machine_col)
            evidence.append("machine")
    if any(term in q for term in ["nguyen nhan", "nguy?n nh?n", "loi", "su co", "ton that"]):
        if loss_name_col and not any(term in q for term in ["nhom ton that", "nhom", "nh?m"]):
            dims.append(loss_name_col)
            evidence.append("loss name")
    if "bao tri" in q and any(term in q for term in ["truong hop", "cac ", "nhung "]):
        if loss_name_col:
            dims.append(loss_name_col)
            evidence.append("loss names inside Bao tri")
    elif any(term in q for term in ["nhom", "nh?m", "bao tri", "san xuat"]):
        if loss_group_col:
            dims.append(loss_group_col)
            evidence.append("loss group")
    unique = []
    for dim in dims:
        if dim and dim not in unique:
            unique.append(dim)
    if unique:
        return DetectionResult(unique, 0.90, evidence)
    return DetectionResult([], 0.0)
