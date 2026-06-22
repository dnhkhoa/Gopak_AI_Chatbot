from __future__ import annotations

from src.rendering.formatters import format_vn_number


SUGGESTION_FALLBACK = [
    "Tổng downtime là bao nhiêu?",
    "Máy nào downtime cao nhất?",
    "Top 5 nguyên nhân tổn thất",
    "Vẽ downtime theo ngày",
    "Tạo dashboard tổng quan",
]


def schema_suggestions(catalog: dict) -> list[str]:
    suggestions = []
    for table in catalog.get("tables", []):
        roles = {col.get("semantic_role") for col in table.get("columns", [])}
        if "duration_seconds" in roles and "machine" in roles:
            suggestions.extend(SUGGESTION_FALLBACK[:4])
            break
    return suggestions or SUGGESTION_FALLBACK


def readable_table_name(table: dict) -> str:
    source = str(table.get("source", ""))
    if "Machine_Downtime" in source:
        return "Downtime máy"
    if "Loss_Assignment" in source:
        return "Phân loại tổn thất"
    if "EntryTransaction" in source:
        return "Ra vào cổng"
    return str(table.get("table_name", "Bảng dữ liệu"))


def row_count_text(row_count: int) -> str:
    return f"{format_vn_number(row_count, 0)} bản ghi"

