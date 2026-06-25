from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.rendering.labels import LABEL_REGISTRY, display_label


# Backwards-compatible alias. The single source of truth is
# ``src.rendering.labels.LABEL_REGISTRY``; do not add new entries here.
COLUMN_LABELS = LABEL_REGISTRY


def format_vn_number(value: Any, decimals: int = 2, strip_zero: bool = True) -> str:
    if value is None:
        return "Không có dữ liệu"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "Không có dữ liệu"
    decimals = max(0, min(decimals, 2))
    text = f"{number:,.{decimals}f}"
    if strip_zero and decimals:
        text = text.rstrip("0").rstrip(".")
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def format_duration(seconds: Any) -> dict[str, str | None]:
    try:
        total_seconds = float(seconds)
    except (TypeError, ValueError):
        return {"primary": "Không có dữ liệu", "secondary": None}
    if not math.isfinite(total_seconds) or total_seconds < 0:
        return {"primary": "Không có dữ liệu", "secondary": None}

    rounded = int(round(total_seconds))
    days, rem = divmod(rounded, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    if rounded < 60:
        primary = f"{rounded} giây"
    elif rounded < 3600:
        primary = f"{minutes} phút {secs} giây" if secs else f"{minutes} phút"
    elif rounded < 86400:
        primary = f"{hours} giờ {minutes} phút" if minutes else f"{hours} giờ"
    else:
        primary = f"{format_vn_number(total_seconds / 3600, 2, False)} giờ"

    parts = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if minutes:
        parts.append(f"{minutes} phút")
    if secs or not parts:
        parts.append(f"{secs} giây")
    return {"primary": primary, "secondary": " ".join(parts)}


def humanize_column_name(column: str, catalog: dict | None = None) -> str:
    return display_label(column, catalog)


def is_duration_column(column: str) -> bool:
    lowered = column.lower()
    return lowered.endswith("_duration_seconds") or lowered.endswith("_seconds") or "thoi_luong" in lowered or "duration" in lowered


def format_cell(value: Any, column: str) -> Any:
    if is_duration_column(column):
        return format_duration(value)["primary"]
    if column.lower() in {"percentage", "percent", "pct"} or "ty_le" in column.lower():
        return f"{format_vn_number(value, 2)}%"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_vn_number(value, 2)
    return value


def format_dataframe_for_display(df: pd.DataFrame, catalog: dict | None = None) -> pd.DataFrame:
    display = df.copy()
    for column in display.columns:
        display[column] = display[column].map(lambda value, col=column: format_cell(value, col))
    return display.rename(columns={column: humanize_column_name(column, catalog) for column in display.columns})


def short_source_name(source: str) -> str:
    return source.replace(".xlsx /", ".xlsx · Sheet")
