from __future__ import annotations

import math
from typing import Any

import pandas as pd


COLUMN_LABELS = {
    "total_duration_seconds": "Tổng thời gian downtime",
    "avg_duration_seconds": "Thời gian downtime trung bình",
    "duration_seconds": "Thời lượng",
    "thoi_luong_seconds": "Thời lượng",
    "thoi_luong": "Thời lượng",
    "machine_name": "Máy",
    "may": "Máy",
    "loss_name": "Nguyên nhân tổn thất",
    "ten_ton_that": "Nguyên nhân tổn thất",
    "loss_group": "Nhóm tổn thất",
    "nhom_ton_that": "Nhóm tổn thất",
    "loss_type": "Loại tổn thất",
    "loai_ton_that": "Loại tổn thất",
    "record_count": "Số lần ghi nhận",
    "row_count": "Số lần ghi nhận",
    "cong": "Cổng",
    "loai_truy_cap": "Loại truy cập",
    "thoi_gian_thuc_thi": "Thời gian thực thi",
    "thoi_gian_bat_dau": "Thời gian bắt đầu",
    "thoi_gian_ket_thuc": "Thời gian kết thúc",
    "gia_tri_can": "Giá trị cân",
}


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
    if column in COLUMN_LABELS:
        return COLUMN_LABELS[column]
    if catalog:
        for table in catalog.get("tables", []):
            for item in table.get("columns", []):
                if item.get("normalized_name") == column and item.get("original_name"):
                    return str(item["original_name"])
    cleaned = column.replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else column


def is_duration_column(column: str) -> bool:
    lowered = column.lower()
    return lowered.endswith("_duration_seconds") or lowered.endswith("_seconds") or "thoi_luong" in lowered or "duration" in lowered


def format_cell(value: Any, column: str) -> Any:
    if is_duration_column(column):
        return format_duration(value)["primary"]
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

