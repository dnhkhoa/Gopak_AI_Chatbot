from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import calendar
import re
from typing import Any

import pandas as pd

from src.query.schemas import FilterSpec
from src.query_understanding.catalog_utils import column_info
from src.query_understanding.schemas import DetectionResult
from src.query_understanding.text import normalize_text


@dataclass
class TimeResolution:
    filters: list[FilterSpec]
    granularity: str | None
    confidence: float
    evidence: list[str]


def resolve_time(question: str, table: dict, start_time_col: str | None) -> TimeResolution:
    if not start_time_col:
        return TimeResolution([], None, 0.0, [])
    q = normalize_text(question)
    evidence: list[str] = []
    filters: list[FilterSpec] = []
    granularity = _granularity(q)
    if granularity:
        evidence.append(f"group by {granularity}")

    bounds = _data_bounds(table, start_time_col)
    resolved = _explicit_range(q) or _explicit_month(q) or _data_relative(q, bounds) or _calendar_relative(q)
    if resolved:
        start, end, reason = resolved
        filters.append(FilterSpec(column=start_time_col, operator="date_between", value=[start.isoformat(), end.isoformat()]))
        evidence.append(reason)
    confidence = 0.92 if filters or granularity else 0.0
    return TimeResolution(filters, granularity, confidence, evidence)


def detect_time(question: str, table: dict, start_time_col: str | None) -> DetectionResult:
    resolution = resolve_time(question, table, start_time_col)
    return DetectionResult(resolution, resolution.confidence, resolution.evidence)


def _granularity(q: str) -> str | None:
    if "theo ngay" in q or "ngay co" in q or "by day" in q or "per day" in q or "daily" in q:
        return "day"
    if "theo tuan" in q or "by week" in q or "per week" in q:
        return "week"
    if "theo thang" in q or "theo th?ng" in q or "giua cac thang" in q or "tung thang" in q or "t?ng th?ng" in q or "moi thang" in q or "by month" in q or "per month" in q or "monthly" in q:
        return "month"
    if "theo nam" in q:
        return "year"
    return None


def _data_bounds(table: dict, column: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    info = column_info(table, column)
    if not info:
        return None
    try:
        return pd.Timestamp(info.get("min")), pd.Timestamp(info.get("max"))
    except Exception:
        return None


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _explicit_month(q: str) -> tuple[date, date, str] | None:
    match = re.search(r"thang\s*(\d{1,2})(?:\s*/\s*(20\d{2}))?", q)
    if not match:
        return None
    month = int(match.group(1))
    if not 1 <= month <= 12:
        return None
    year = int(match.group(2)) if match.group(2) else (2025 if month >= 11 else 2026)
    start, end = _month_range(year, month)
    return start, end, f"explicit month {year}-{month:02d}"


def _explicit_range(q: str) -> tuple[date, date, str] | None:
    dates = re.findall(r"(20\d{2})-(\d{1,2})-(\d{1,2})", q)
    if len(dates) >= 2:
        y1, m1, d1 = map(int, dates[0])
        y2, m2, d2 = map(int, dates[1])
        start = date(y1, m1, d1)
        # The user-facing end date is inclusive; SQL date_between is inclusive too,
        # but using next day matches existing oracle half-open ranges.
        end = date(y2, m2, d2) + timedelta(days=1)
        return start, end, "explicit date range"
    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match and "thang" not in q:
        year = int(year_match.group(1))
        return date(year, 1, 1), date(year + 1, 1, 1), f"explicit year {year}"
    return None


def _data_relative(q: str, bounds: tuple[pd.Timestamp, pd.Timestamp] | None) -> tuple[date, date, str] | None:
    if not bounds:
        return None
    min_ts, max_ts = bounds
    if "thang dau tien" in q or "ky dau" in q:
        start, end = _month_range(min_ts.year, min_ts.month)
        return start, end, "first month in data"
    if "thang gan nhat" in q or "ky cuoi" in q:
        start, end = _month_range(max_ts.year, max_ts.month)
        return start, end, "latest month in data"
    if "ngay dau tien" in q:
        start = min_ts.date()
        return start, start + timedelta(days=1), "first day in data"
    if "ngay gan nhat" in q:
        start = max_ts.date()
        return start, start + timedelta(days=1), "latest day in data"
    if "tuan gan nhat" in q:
        start = (max_ts - pd.Timedelta(days=max_ts.weekday())).date()
        return start, start + timedelta(days=7), "latest week in data"
    if "hai thang gan nhat" in q:
        latest_start, latest_end = _month_range(max_ts.year, max_ts.month)
        prev_year, prev_month = (latest_start.year - 1, 12) if latest_start.month == 1 else (latest_start.year, latest_start.month - 1)
        prev_start, _ = _month_range(prev_year, prev_month)
        return prev_start, latest_end, "last two months in data"
    return None


def _calendar_relative(q: str) -> tuple[date, date, str] | None:
    today = date.today()
    if "hom nay" in q:
        return today, today + timedelta(days=1), "calendar today"
    if "thang nay" in q:
        start, end = _month_range(today.year, today.month)
        return start, end, "calendar current month"
    if "thang truoc" in q:
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        start, end = _month_range(year, month)
        return start, end, "calendar previous month"
    if "nam nay" in q:
        return date(today.year, 1, 1), date(today.year + 1, 1, 1), "calendar current year"
    return None
