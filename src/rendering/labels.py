"""Single source of truth for customer-facing display labels (P0-A).

Separates the four name concepts the rest of the app must keep distinct:

    canonical_name   - stable internal id (e.g. ``total_duration_seconds``)
    normalized_name  - accent-insensitive / snake_case key for matching only
    display_name_vi  - the ONLY string allowed to reach customer UI
    source_name      - the original Excel header, kept for provenance/audit

``DisplayLabelRegistry`` resolves any internal key to ``display_name_vi`` using,
in order: an explicit registry, the catalog's original Excel header, the column's
semantic role, metric-alias decomposition (``sum_x`` -> ``Tổng <x>``), and finally
a humanized fallback. It never emits a raw snake_case key or an un-accented label
for a key it recognizes.

The leak-detection helpers here back the LocalizationValidator / MetadataLeakage
validators; they are a *backstop*, not the primary mechanism.
"""
from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel


class FieldIdentity(BaseModel):
    canonical_name: str
    normalized_name: str
    display_name_vi: str
    source_name: str | None = None


# --- Vietnamese labels for known canonical / normalized keys -----------------
# Superset of the historical COLUMN_LABELS plus insight metric keys.
LABEL_REGISTRY: dict[str, str] = {
    # overview / insight tables
    "PHAT HIEN": "Phát hiện",
    "phat hien": "Phát hiện",
    "DOI TUONG": "Đối tượng",
    "doi tuong": "Đối tượng",
    "CHI SO": "Chỉ số",
    "chi so": "Chỉ số",
    "GIA TRI": "Giá trị",
    "gia tri": "Giá trị",
    "machine_total_downtime": "Tổng downtime theo máy",
    "cause_total_downtime": "Tổng downtime theo nguyên nhân",
    "daily_total_downtime": "Tổng downtime theo ngày",
    # durations / downtime
    "downtime_duration": "thời gian downtime",
    "total_duration_seconds": "Tổng thời gian downtime",
    "avg_duration_seconds": "Thời gian downtime trung bình",
    "sum_duration_seconds": "Tổng thời gian downtime",
    "duration_seconds": "Thời lượng",
    "thoi_luong_seconds": "Thời lượng",
    "sum_thoi_luong_seconds": "Tổng thời lượng",
    "avg_thoi_luong_seconds": "Thời lượng trung bình",
    "thoi_luong": "Thời lượng",
    "duration_reported_seconds": "Thời lượng báo cáo",
    "duration_calculated_seconds": "Thời lượng tính toán",
    "duration_difference_seconds": "Chênh lệch thời lượng",
    # machine / loss domain
    "machine_name": "Máy",
    "may": "Máy",
    "machine": "Máy",
    "loss_name": "Nguyên nhân tổn thất",
    "ten_ton_that": "Nguyên nhân tổn thất",
    "loss_group": "Nhóm tổn thất",
    "nhom_ton_that": "Nhóm tổn thất",
    "loss_type": "Loại tổn thất",
    "loai_ton_that": "Loại tổn thất",
    # transaction domain
    "gia_tri_can": "Giá trị cân",
    "sum_gia_tri_can": "Tổng giá trị cân",
    "avg_gia_tri_can": "Giá trị cân trung bình",
    "transaction_count": "Số giao dịch",
    "transaction_value": "Giá trị giao dịch",
    "cong": "Cổng",
    "loai_truy_cap": "Loại truy cập",
    "loai_xe": "Loại xe",
    "cong_ty_van_tai": "Công ty vận tải",
    "cong_ty_chu_quan": "Công ty chủ quản",
    "ho_va_ten": "Họ và tên",
    # generic counts / time
    "record_count": "Số bản ghi",
    "row_count": "Số bản ghi",
    "count": "Số lượng",
    "percentage": "Tỷ lệ",
    "date_range": "Phạm vi thời gian",
    "thoi_gian_thuc_thi": "Thời gian thực thi",
    "thoi_gian_bat_dau": "Thời gian bắt đầu",
    "thoi_gian_ket_thuc": "Thời gian kết thúc",
}

# Semantic role -> Vietnamese display label (used when no explicit key match).
SEMANTIC_ROLE_LABELS: dict[str, str] = {
    "machine": "Máy",
    "loss_name": "Nguyên nhân tổn thất",
    "loss_group": "Nhóm tổn thất",
    "loss_type": "Loại tổn thất",
    "duration": "Thời lượng",
    "duration_seconds": "Thời lượng",
    "duration_reported_seconds": "Thời lượng báo cáo",
    "duration_calculated_seconds": "Thời lượng tính toán",
    "duration_difference_seconds": "Chênh lệch thời lượng",
    "start_time": "Thời gian bắt đầu",
    "end_time": "Thời gian kết thúc",
    "record_no": "Số thứ tự",
}

# Aggregation prefixes -> Vietnamese qualifier.
AGG_PREFIX_LABELS: list[tuple[str, str]] = [
    ("total_", "Tổng"),
    ("sum_", "Tổng"),
    ("avg_", "Trung bình"),
    ("mean_", "Trung bình"),
    ("min_", "Nhỏ nhất"),
    ("max_", "Lớn nhất"),
    ("count_", "Số lượng"),
]

_SECONDS_SUFFIX = "_seconds"

# Internal tokens that must never appear in customer-facing strings.
INTERNAL_ENUM_NAMES: set[str] = {
    "DETERMINISTIC", "REAL_LLM", "SEMANTIC", "SAFE_FAILURE", "REFUSAL",
    "CLARIFICATION", "NEW_REQUEST", "FOLLOW_UP_ON_PREVIOUS_RESULT", "REFINEMENT",
    "ANALYTICAL_QUERY", "DASHBOARD_REQUEST", "UNSUPPORTED_BY_ACTIVE_FILE",
    "DETERMINISTIC_REPORT", "MODEL_UNAVAILABLE", "QUERY_TIMEOUT",
    "real_llm_candidate", "generic_tabular",
}

# Un-accented stems of Vietnamese words that, standing alone as ASCII tokens,
# indicate a stripped-diacritic label leaked to the UI. Conservative on purpose.
_UNACCENTED_VI_STEMS: set[str] = {
    "tong", "quan", "du", "lieu", "phat", "hien", "doi", "tuong", "chi", "so",
    "gia", "tri", "thoi", "gian", "phan", "tich", "ton", "that", "nhom", "may",
    "nguyen", "nhan", "bao", "cao", "luong", "pham", "vi", "cong", "truy", "cap",
}

_SNAKE_KEY_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_WORD_RE = re.compile(r"[A-Za-zÀ-ỹ]+")


def _humanize_fallback(name: str) -> str:
    cleaned = name.replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else name


def _catalog_original_name(name: str, catalog: dict | None) -> str | None:
    if not catalog:
        return None
    for table in catalog.get("tables", []):
        for item in table.get("columns", []):
            if item.get("normalized_name") == name and item.get("original_name"):
                return str(item["original_name"])
    return None


def _catalog_role(name: str, catalog: dict | None) -> str | None:
    if not catalog:
        return None
    for table in catalog.get("tables", []):
        for item in table.get("columns", []):
            if item.get("normalized_name") == name and item.get("semantic_role"):
                return str(item["semantic_role"])
    return None


def display_label(name: str | None, catalog: dict | None = None, role: str | None = None) -> str:
    """Resolve any internal key to a Vietnamese display label."""
    if name is None:
        return ""
    key = str(name).strip()
    if not key:
        return ""
    # 1. explicit registry
    if key in LABEL_REGISTRY:
        return LABEL_REGISTRY[key]
    lowered = key.lower()
    if lowered in LABEL_REGISTRY:
        return LABEL_REGISTRY[lowered]
    # 2. original Excel header (already accented Vietnamese)
    original = _catalog_original_name(key, catalog)
    if original:
        return original
    # 3. semantic role
    role = role or _catalog_role(key, catalog)
    if role and role in SEMANTIC_ROLE_LABELS:
        return SEMANTIC_ROLE_LABELS[role]
    # 4. metric-alias decomposition: <agg>_<base>
    for prefix, qualifier in AGG_PREFIX_LABELS:
        if lowered.startswith(prefix):
            base = key[len(prefix):]
            base_label = display_label(base, catalog)
            return f"{qualifier} {base_label[:1].lower() + base_label[1:]}" if base_label else _humanize_fallback(key)
    # ..._seconds duration columns
    if lowered.endswith(_SECONDS_SUFFIX):
        base = key[: -len(_SECONDS_SUFFIX)]
        base_label = display_label(base, catalog)
        if base in LABEL_REGISTRY or _catalog_original_name(base, catalog):
            return base_label
    # 5. humanized fallback (last resort)
    return _humanize_fallback(key)


def field_identity(name: str, catalog: dict | None = None, role: str | None = None,
                   source_name: str | None = None) -> FieldIdentity:
    return FieldIdentity(
        canonical_name=name,
        normalized_name=str(name).lower(),
        display_name_vi=display_label(name, catalog, role),
        source_name=source_name or _catalog_original_name(name, catalog),
    )


# --- leak detection backstop -------------------------------------------------

def find_internal_keys(text: str) -> list[str]:
    """Return snake_case keys / internal enum names found in a customer string."""
    if not text:
        return []
    hits: list[str] = []
    for match in _SNAKE_KEY_RE.findall(text):
        # ignore values that are obviously not field keys (e.g. file ids handled elsewhere)
        if match.startswith("_"):
            continue
        hits.append(match)
    for token in re.findall(r"\b[A-Z][A-Z_]{3,}\b", text):
        if token in INTERNAL_ENUM_NAMES:
            hits.append(token)
    return sorted(set(hits))


def find_unaccented_vietnamese(text: str) -> list[str]:
    """Return diacritic-stripped Vietnamese phrases leaked to the UI.

    Flags runs of two or more adjacent ASCII tokens that are all known stripped
    Vietnamese stems (e.g. "Tong quan", "PHAT HIEN", "Gia tri"). Requiring a run
    avoids false positives on isolated English words like "may"/"so".
    """
    if not text:
        return []
    hits: list[str] = []
    run: list[str] = []
    for word in _WORD_RE.findall(text):
        lw = word.lower()
        if lw.isascii() and lw in _UNACCENTED_VI_STEMS:
            run.append(word)
            continue
        if len(run) >= 2:
            hits.append(" ".join(run))
        run = []
    if len(run) >= 2:
        hits.append(" ".join(run))
    return sorted(set(hits))


def scan_label_leaks(text: str) -> dict[str, list[str]]:
    return {
        "internal_keys": find_internal_keys(text or ""),
        "unaccented_vietnamese": find_unaccented_vietnamese(text or ""),
    }
