from __future__ import annotations

from datetime import time, timedelta
from hashlib import sha1
import math
import re
import unicodedata
from typing import Iterable

import pandas as pd


def strip_accents(value: str) -> str:
    value = str(value).replace("đ", "d").replace("Đ", "D").replace("Ä‘", "d").replace("Ä", "D")
    text = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_column_name(name: object, fallback_index: int = 0) -> str:
    raw = "" if name is None else str(name).strip()
    if not raw or raw.lower().startswith("unnamed"):
        raw = f"column_{fallback_index + 1}"
    text = strip_accents(raw).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        text = f"column_{fallback_index + 1}"
    if text[0].isdigit():
        text = f"col_{text}"
    return text


def make_unique(names: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    output: list[str] = []
    for name in names:
        count = seen.get(name, 0)
        seen[name] = count + 1
        output.append(name if count == 0 else f"{name}_{count + 1}")
    return output


def normalize_columns(original_columns: Iterable[object]) -> dict[str, str]:
    original = ["" if c is None else str(c).strip() for c in original_columns]
    normalized = make_unique([normalize_column_name(c, i) for i, c in enumerate(original)])
    return dict(zip(original, normalized))


def parse_duration_seconds(value: object) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1_000_000
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return float(value * 86400 if value <= 3 else value * 60)
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"(?:(\d+)\s+)?(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?", text)
    if match:
        days = int(match.group(1) or 0)
        hours = int(match.group(2))
        minutes = int(match.group(3))
        seconds = int(match.group(4) or 0)
        return float(days * 86400 + hours * 3600 + minutes * 60 + seconds)
    numeric = re.fullmatch(r"\d+(?:[.,]\d+)?", text)
    if numeric:
        return float(text.replace(",", ".")) * 60
    return None


def parse_datetime_series(series: pd.Series) -> pd.Series:
    dayfirst = pd.to_datetime(series, errors="coerce", dayfirst=True)
    monthfirst = pd.to_datetime(series, errors="coerce", dayfirst=False)
    return dayfirst if dayfirst.notna().mean() >= monthfirst.notna().mean() else monthfirst


def stable_table_name(source_file: str, source_sheet: str) -> str:
    stem = normalize_column_name(source_file.rsplit(".", 1)[0])
    sheet = normalize_column_name(source_sheet)
    digest = sha1(f"{source_file}:{source_sheet}".encode("utf-8")).hexdigest()[:6]
    return f"{stem}_{sheet}_{digest}"


SEMANTIC_ALIASES = {
    "record_no": {"no", "record_no", "stt"},
    "machine": {"may", "machine", "machine_name", "ten_may"},
    "duration": {"thoi_luong", "duration", "downtime", "time_loss"},
    "start_time": {"thoi_gian_bat_dau", "start", "start_time"},
    "end_time": {"thoi_gian_ket_thuc", "end", "end_time"},
    "loss_name": {"ten_ton_that", "loss", "reason", "nguyen_nhan"},
    "loss_group": {"nhom_ton_that", "group", "category", "bo_phan"},
    "loss_type": {"loai_ton_that", "type"},
}


def infer_semantic_role(column_name: str, original_name: str = "") -> str | None:
    haystack = f"{column_name} {strip_accents(original_name).lower()}"
    for role, aliases in SEMANTIC_ALIASES.items():
        if any(alias in haystack for alias in aliases):
            return role
    return None
