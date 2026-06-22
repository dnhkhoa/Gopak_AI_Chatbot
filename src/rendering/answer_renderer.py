from __future__ import annotations

import pandas as pd

from src.query.schemas import QueryPlan
from src.rendering.formatters import format_duration, format_vn_number


def render_text_answer(question: str, plan: QueryPlan, df: pd.DataFrame) -> str:
    if plan.intent == "clarification":
        return plan.clarification_question or "Bạn có thể hỏi rõ hơn về bảng, cột hoặc khoảng thời gian cần phân tích không?"
    if df.empty:
        return "Không tìm thấy dữ liệu phù hợp với điều kiện đã chọn."
    if len(df) == 1 and len(df.columns) == 1:
        return format_value(df.iloc[0, 0])
    return f"Có {format_vn_number(len(df), 0)} dòng kết quả phù hợp."


def format_value(value) -> str:
    if isinstance(value, float):
        if abs(value) >= 60:
            return format_duration(value)["primary"]
        return format_vn_number(value, 2)
    return str(value)

