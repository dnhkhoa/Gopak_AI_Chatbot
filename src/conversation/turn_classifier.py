from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.query_understanding.text import normalize_text


class TurnType(StrEnum):
    NEW_QUERY = "NEW_QUERY"
    REFINE_PREVIOUS = "REFINE_PREVIOUS"
    ADD_FILTER = "ADD_FILTER"
    REMOVE_FILTER = "REMOVE_FILTER"
    CHANGE_TIME = "CHANGE_TIME"
    CHANGE_METRIC = "CHANGE_METRIC"
    CHANGE_DIMENSION = "CHANGE_DIMENSION"
    CHANGE_RANKING = "CHANGE_RANKING"
    CHANGE_OUTPUT = "CHANGE_OUTPUT"
    REFERENCE_ENTITY = "REFERENCE_ENTITY"
    REFERENCE_RESULT = "REFERENCE_RESULT"
    RESET_CONTEXT = "RESET_CONTEXT"


@dataclass
class TurnClassification:
    turn_type: TurnType
    confidence: float
    reason: str


def classify_turn(question: str, has_state: bool) -> TurnClassification:
    q = normalize_text(question)
    if any(term in q for term in ["xoa toan bo bo loc", "xoa bo loc", "reset ngu canh", "bat dau lai"]):
        return TurnClassification(TurnType.RESET_CONTEXT, 0.98, "Explicit reset/remove all context phrase.")
    if any(term in q for term in ["ket qua vua roi", "ket qua tren", "du lieu tren", "top vua roi"]):
        return TurnClassification(TurnType.REFERENCE_RESULT, 0.92, "References previous result.")
    if any(term in q for term in ["may do", "may dung dau", "nguyen nhan dung dau", "nhom do", "nhom tren", "hai thang do"]):
        return TurnClassification(TurnType.REFERENCE_ENTITY, 0.94, "References an entity from prior result.")
    if any(term in q for term in ["chi lay thang", "hai thang gan nhat", "thang gan nhat", "thang dau tien", "ngay gan nhat"]):
        return TurnClassification(TurnType.CHANGE_TIME, 0.95, "Time-only refinement.")
    if any(term in q for term in ["xoa filter", "bo filter", "xoa dieu kien", "bo dieu kien"]):
        return TurnClassification(TurnType.REMOVE_FILTER, 0.90, "Remove filter phrase.")
    if any(term in q for term in ["chi giu", "chi lay", "loc", "tren 1 gio", "tren mot gio", "tren 30 phut"]):
        return TurnClassification(TurnType.ADD_FILTER, 0.86, "Filter refinement phrase.")
    ranking_words = ["top", "bottom", "dung dau", "cao nhat", "thap nhat", "nhieu nhat", "it nhat", "pho bien", "xep hang"]
    dim_nouns = ["may", "machine", "nguyen nhan", "ton that", "nhom", "cong", "loai", "thang", "ngay"]
    output_words = ["bieu do", "chart", "ve cot", "ve line", "ve chart", "ve bieu do", "excel", "bao cao", "dashboard", "xuat excel", "xuat file", "xuat bao cao", "xuat ket qua", "xuat ra"]
    metric_words = ["downtime", "tong", "so lan", "dem", "ty le", "ty trong", "phan tram", "trung binh", "thoi gian", "thoi luong"]
    self_contained_output = (
        any(term in q for term in output_words)
        and (
            any(d in q for d in dim_nouns)
            or any(m in q for m in metric_words)
            or any(term in q for term in ["xu huong", "qua thoi gian", "theo thoi gian", "phan bo", "tong quan"])
        )
    )
    if self_contained_output and not any(term in q for term in ["ket qua vua roi", "ket qua tren", "du lieu tren", "top vua roi"]):
        return TurnClassification(TurnType.NEW_QUERY, 0.92, "Self-contained output/report/chart request.")
    # A self-contained ranking question that names its own dimension is a NEW query,
    # not a refinement of the previous result. Checked before output/ranking refinements.
    if any(w in q for w in ranking_words) and any(d in q for d in dim_nouns):
        return TurnClassification(TurnType.NEW_QUERY, 0.90, "Complete ranking query naming its own dimension.")
    if any(term in q for term in output_words):
        return TurnClassification(TurnType.CHANGE_OUTPUT, 0.88, "Output change phrase.")
    if any(term in q for term in ranking_words):
        return TurnClassification(TurnType.CHANGE_RANKING, 0.86, "Ranking change phrase.")
    if any(term in q for term in ["trung binh", "tong", "so lan", "dem", "ty le", "ty trong", "phan tram"]):
        return TurnClassification(TurnType.CHANGE_METRIC if has_state else TurnType.NEW_QUERY, 0.82 if has_state else 0.78, "Metric phrase.")
    if any(term in q for term in ["theo may", "theo nguyen nhan", "theo nhom", "theo ngay", "theo thang"]):
        return TurnClassification(TurnType.CHANGE_DIMENSION if has_state else TurnType.NEW_QUERY, 0.82 if has_state else 0.78, "Dimension phrase.")
    if has_state and len(q.split()) <= 7:
        return TurnClassification(TurnType.REFINE_PREVIOUS, 0.60, "Short follow-up with active state.")
    return TurnClassification(TurnType.NEW_QUERY, 0.75, "Independent query.")
