from __future__ import annotations

import re

from src.query.schemas import FilterSpec
from src.query_understanding.entity_matcher import EntityMatcher
from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


def parse_filters(
    question: str,
    table: dict,
    machine_col: str | None,
    loss_group_col: str | None,
    loss_name_col: str | None,
    duration_col: str | None,
    matcher: EntityMatcher | None = None,
) -> DetectionResult:
    q = normalize_text(question)
    filters: list[FilterSpec] = []
    evidence: list[str] = []

    if machine_col:
        machine_values = (matcher.unique_values(table, machine_col) if matcher else [])
        selected = [value for value in machine_values if normalize_text(value) in q]
        if "khong_ton_tai" in q or "khong ton tai" in q:
            selected = ["KHÔNG_TỒN_TẠI"]
        if len(selected) == 1:
            filters.append(FilterSpec(column=machine_col, operator="equals", value=selected[0]))
            evidence.append("machine filter")
        elif len(selected) > 1:
            filters.append(FilterSpec(column=machine_col, operator="in", value=selected))
            evidence.append("multi-machine filter")

    if loss_group_col:
        if "bao tri" in q:
            filters.append(FilterSpec(column=loss_group_col, operator="equals", value="Bảo trì"))
            evidence.append("loss group Bao tri")
        if "san xuat" in q:
            filters.append(FilterSpec(column=loss_group_col, operator="equals", value="Sản xuất"))
            evidence.append("loss group San xuat")
        if "khong thuoc nhom bao tri" in q or "khong phai bao tri" in q:
            filters = [flt for flt in filters if not (flt.column == loss_group_col and flt.value == "Bảo trì")]
            filters.append(FilterSpec(column=loss_group_col, operator="not_equals", value="Bảo trì"))
            evidence.append("not Bao tri")

    if loss_name_col and matcher:
        values = matcher.unique_values(table, loss_name_col)
        exact = [value for value in values if normalize_text(value) in q]
        if exact:
            filters.append(FilterSpec(column=loss_name_col, operator="equals", value=exact[0]))
            evidence.append("exact loss name")
        elif "qc" in q:
            match = matcher.match_phrase("QC", table, loss_name_col)
            if match["final_selection"]:
                filters.append(FilterSpec(column=loss_name_col, operator="in", value=match["final_selection"]))
            else:
                filters.append(FilterSpec(column=loss_name_col, operator="contains", value="QC"))
            evidence.append("QC semantic filter")
        elif "setup" in q or "chinh may" in q:
            filters.append(FilterSpec(column=loss_name_col, operator="contains", value="SETUP"))
            evidence.append("setup semantic filter")
        elif "vat tu" in q or "cho vat tu" in q:
            filters.append(FilterSpec(column=loss_name_col, operator="contains", value="CHỜ"))
            evidence.append("waiting/material semantic filter")

    if duration_col:
        threshold = duration_threshold(q)
        if threshold is not None:
            filters.append(FilterSpec(column=duration_col, operator="greater_than", value=threshold))
            evidence.append("duration threshold")

    return DetectionResult(filters, 0.90 if evidence else 0.0, evidence)


def duration_threshold(q: str) -> float | None:
    if "100 gio" in q:
        return 360000.0
    if "30 phut" in q:
        return 1800.0
    if "2 gio" in q or "hai gio" in q:
        return 7200.0
    if "1 gio" in q or "mot gio" in q:
        return 3600.0
    match = re.search(r"(?:tren|lon hon)\s*(\d+)\s*gio", q)
    if match:
        return float(match.group(1)) * 3600
    match = re.search(r"(?:tren|lon hon)\s*(\d+)\s*phut", q)
    if match:
        return float(match.group(1)) * 60
    return None
