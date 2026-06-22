from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from time import perf_counter
from typing import Any
from uuid import uuid4

import pandas as pd

from src.application.schemas import ChatResponse, TablePayload


def try_row_level_response(conversation_id: str, message: str, catalog: dict, state, debug: bool, started: float) -> ChatResponse | None:
    table = (catalog.get("tables") or [None])[0]
    if not table:
        return None
    df = pd.read_parquet(table["parquet_path"])
    roles = _role_columns(table)
    q = _norm(message)

    if _asks_operating_time(q):
        return _simple(
            conversation_id,
            "clarification",
            "Can xac nhan gia dinh van hanh",
            "File dang chon chi ghi nhan cac khoang downtime. Minh co the liet ke khoang khong co downtime, nhung dieu do khong chung minh may dang hoat dong neu chua xac nhan lich chay va do day du cua du lieu.",
            "OPERATING_TIME_CLARIFICATION",
            state,
            debug,
            started,
            {"generated_sql": None},
        )

    record_range = _record_range(q)
    if record_range:
        start, end = record_range
        out = df[(pd.to_numeric(df.get("_record_no"), errors="coerce") >= start) & (pd.to_numeric(df.get("_record_no"), errors="coerce") <= end)].copy()
        return _records_response(conversation_id, out, "record_table", f"Records No. {start}-{end}", state, debug, started, "RECORD_RANGE", "record_no")

    record_no = _record_no(q)
    if record_no is not None:
        out = df[pd.to_numeric(df.get("_record_no"), errors="coerce") == record_no].copy()
        return _records_response(conversation_id, out, "record_detail", f"Record No. {record_no}", state, debug, started, "RECORD_LOOKUP", "record_no")

    excel_row = _excel_row(q)
    if excel_row is not None:
        out = df[pd.to_numeric(df.get("_source_excel_row"), errors="coerce") == excel_row].copy()
        return _records_response(conversation_id, out, "record_detail", f"Excel row {excel_row}", state, debug, started, "RECORD_LOOKUP", "source_excel_row")

    data_index = _data_row_index(q)
    if data_index is not None:
        out = df[pd.to_numeric(df.get("_data_row_index"), errors="coerce") == data_index].copy()
        response = _records_response(conversation_id, out, "record_detail", f"Data row {data_index}", state, debug, started, "FIRST_RECORD" if data_index == 1 else "RECORD_LOOKUP", "data_row_index")
        if response.summary:
            response.summary = "Interpreted row as the normalized data record after the detected header. " + response.summary
        return response

    if any(term in q for term in ["gan nhat", "latest", "cuoi cung"]) and _asks_latest_record(q):
        machine = _machine_filter(q, df, roles.get("machine"))
        if machine == "__AMBIGUOUS__":
            return _machine_clarification(conversation_id, state, debug, started)
        out = _filter_machine(df, roles.get("machine"), machine)
        out = out.sort_values(roles.get("start_time") or "_data_row_index", ascending=False).head(1)
        return _records_response(conversation_id, out, "record_detail", "Latest event", state, debug, started, "LAST_RECORD", "datetime_desc")

    if any(term in q for term in ["som nhat", "earliest", "dau tien theo thoi gian"]):
        machine = _machine_filter(q, df, roles.get("machine"))
        if machine == "__AMBIGUOUS__":
            return _machine_clarification(conversation_id, state, debug, started)
        out = _filter_machine(df, roles.get("machine"), machine)
        out = out.sort_values(roles.get("start_time") or "_data_row_index", ascending=True).head(1)
        return _records_response(conversation_id, out, "record_detail", "Earliest event", state, debug, started, "FIRST_RECORD", "datetime_asc")

    explicit_date = _parse_date(q, df, roles.get("start_time"))
    if explicit_date and (roles.get("start_time") and roles.get("end_time")):
        if any(term in q for term in ["bao nhieu lan", "may lan", "so lan"]) and not any(term in q for term in ["tu ", "den ", "luc ", "overlap"]):
            return None
        machine = _machine_filter(q, df, roles.get("machine"))
        if machine == "__AMBIGUOUS__":
            return _machine_clarification(conversation_id, state, debug, started)
        day_start, day_end, assumption = explicit_date
        out = _filter_machine(df, roles.get("machine"), machine)
        window = _time_window(q, day_start)
        if window:
            start_dt, end_dt = window
        elif "dang dien ra luc" in q or "luc " in q:
            instant = _instant(q, day_start)
            if instant:
                start_dt, end_dt = instant, instant + timedelta(microseconds=1)
            else:
                start_dt, end_dt = day_start, day_end
        else:
            start_dt, end_dt = day_start, day_end
        out = _interval_overlap(out, roles["start_time"], roles["end_time"], start_dt, end_dt)
        if "dau tien" in q:
            out = out.sort_values(roles["start_time"], ascending=True).head(1)
        elif "gan nhat" in q or "cuoi" in q:
            out = out.sort_values(roles["start_time"], ascending=False).head(1)
        else:
            out = out.sort_values(roles["start_time"], ascending=True)
        if any(term in q for term in ["bao nhieu", "may lan", "so lan", "so record"]):
            return _count_response(conversation_id, out, state, debug, started, "TIME_WINDOW_RECORDS", assumption)
        if any(term in q for term in ["tong cong bao lau", "tong bao lau", "tong downtime", "bao lau"]):
            return _duration_response(conversation_id, out, roles, state, debug, started, "INTERVAL_OVERLAP", start_dt, end_dt, assumption)
        return _records_response(conversation_id, out.head(100), "timeline", "Downtime intervals", state, debug, started, "TIME_WINDOW_RECORDS", "interval_overlap", {"date_assumption": assumption})

    if _asks_duplicate_quality(q):
        out = df[df.get("_is_exact_duplicate") == True].copy() if "_is_exact_duplicate" in df.columns else df.iloc[0:0].copy()
        return _records_response(conversation_id, out.head(100), "record_table", "Duplicate records", state, debug, started, "DATA_QUALITY", "exact_duplicate")

    if any(term in q for term in ["dai hon 24 gio", "hon 24 gio", "> 24 gio"]):
        duration_col = "duration_seconds" if "duration_seconds" in df.columns else roles.get("duration_seconds")
        out = df[df[duration_col] > 86400].copy() if duration_col and duration_col in df.columns else df.iloc[0:0].copy()
        return _records_response(conversation_id, out.head(100), "record_table", "Duration longer than 24 hours", state, debug, started, "DATA_QUALITY", "duration_gt_24h")

    if any(term in q for term in ["start time lon hon end time", "bat dau lon hon ket thuc", "start lon hon end"]):
        start_col, end_col = roles.get("start_time"), roles.get("end_time")
        out = df[df[start_col] > df[end_col]].copy() if start_col and end_col and start_col in df.columns and end_col in df.columns else df.iloc[0:0].copy()
        return _records_response(conversation_id, out.head(100), "record_table", "Negative intervals", state, debug, started, "DATA_QUALITY", "negative_interval")

    if any(term in q for term in ["thieu loss", "thieu ten ton that", "chua duoc phan loai", "is null"]):
        loss_cols = [col for key in ["loss_name", "loss_group", "loss_type"] if (col := roles.get(key))]
        if loss_cols:
            mask = False
            for col in loss_cols:
                mask = mask | df[col].isna()
            out = df[mask].copy()
            return _records_response(conversation_id, out.head(100), "record_table", "Missing loss classification", state, debug, started, "DATA_QUALITY", "missing_classification")

    return None


def _records_response(
    conversation_id: str,
    df: pd.DataFrame,
    response_type: str,
    title: str,
    state,
    debug: bool,
    started: float,
    execution_mode: str,
    lookup_mode: str,
    extra: dict[str, Any] | None = None,
) -> ChatResponse:
    display = _display_records(df)
    summary = f"Found {len(df)} matching record(s)."
    metadata = _metadata(state, debug, started, execution_mode, {"lookup_mode": lookup_mode, "row_count": len(df), **(extra or {})})
    return ChatResponse(
        message_id=str(uuid4()),
        conversation_id=conversation_id,
        response_type=response_type,
        title=title,
        summary=summary,
        table=TablePayload(columns=list(display.columns), rows=_rows(display)),
        metadata=metadata,
    )


def _count_response(conversation_id: str, df: pd.DataFrame, state, debug: bool, started: float, execution_mode: str, assumption: str | None) -> ChatResponse:
    metadata = _metadata(state, debug, started, execution_mode, {"date_assumption": assumption, "aggregation_policy": "raw_record_count"})
    return ChatResponse(
        message_id=str(uuid4()),
        conversation_id=conversation_id,
        response_type="scalar",
        title="Record count",
        summary="Count uses raw records, not deduplicated events.",
        primary_value=str(len(df)),
        metadata=metadata,
    )


def _duration_response(
    conversation_id: str,
    df: pd.DataFrame,
    roles: dict[str, str],
    state,
    debug: bool,
    started: float,
    execution_mode: str,
    window_start: datetime,
    window_end: datetime,
    assumption: str | None,
) -> ChatResponse:
    duration_col = "duration_seconds" if "duration_seconds" in df.columns else roles.get("duration_seconds")
    total = float(df[duration_col].fillna(0).sum()) if duration_col and duration_col in df.columns else 0.0
    metadata = _metadata(
        state,
        debug,
        started,
        execution_mode,
        {
            "date_assumption": assumption,
            "duration_policy": "reported_duration_seconds",
            "interval_mode": "event_overlap_filter",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
    )
    return ChatResponse(
        message_id=str(uuid4()),
        conversation_id=conversation_id,
        response_type="scalar",
        title="Total downtime",
        summary=f"Reported-duration sum across {len(df)} matching record(s).",
        primary_value=_format_seconds(total),
        secondary_value=f"{int(total)} seconds",
        metadata=metadata,
    )


def _simple(conversation_id: str, response_type: str, title: str, summary: str, execution_mode: str, state, debug: bool, started: float, extra: dict[str, Any] | None = None) -> ChatResponse:
    return ChatResponse(
        message_id=str(uuid4()),
        conversation_id=conversation_id,
        response_type=response_type,
        title=title,
        summary=summary,
        metadata=_metadata(state, debug, started, execution_mode, extra or {}),
    )


def _metadata(state, debug: bool, started: float, execution_mode: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_mode": execution_mode,
        "router_confidence": 1.0,
        "routing_reason": "row_level_deterministic",
        "llm_called": False,
        "generated_sql": None,
        "active_file_id": state.active_file_id,
        "active_file_name": state.active_file_name,
        "file_scope_validated": True,
        "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
        "debug": extra if debug else None,
        **extra,
    }


def _role_columns(table: dict) -> dict[str, str]:
    roles: dict[str, str] = {}
    for col in table.get("columns", []):
        role = col.get("semantic_role")
        name = col.get("normalized_name")
        if role and name and role not in roles:
            roles[role] = name
    return roles


def _display_records(df: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "_record_no",
        "_data_row_index",
        "_source_excel_row",
        "may",
        "thoi_gian_bat_dau",
        "thoi_gian_ket_thuc",
        "duration_reported_text",
        "duration_seconds",
        "ten_ton_that",
        "nhom_ton_that",
        "loai_ton_that",
        "note",
        "_source_sheet",
    ]
    cols = [col for col in preferred if col in df.columns]
    if not cols:
        cols = list(df.columns[:12])
    return df[cols].copy()


def _rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for key, value in row.items():
            if pd.isna(value):
                clean[key] = None
            elif isinstance(value, pd.Timestamp):
                clean[key] = value.isoformat()
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        rows.append(clean)
    return rows


def _record_no(q: str) -> int | None:
    patterns = [
        r"\bno\.?\s*(?:bang|=)?\s*(\d+)\b",
        r"\brecord\s*(?:number)?\s*(\d+)\b",
        r"\bban ghi so\s*(\d+)\b",
        r"\bdong co no\.?\s*(?:bang|=)?\s*(\d+)\b",
    ]
    for pattern in patterns:
        if match := re.search(pattern, q):
            return int(match.group(1))
    return None


def _record_range(q: str) -> tuple[int, int] | None:
    match = re.search(r"(?:no|record).*?(\d+)\s*(?:den|toi|-)\s*(?:no|record)?\s*(\d+)", q)
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    return (min(start, end), max(start, end))


def _excel_row(q: str) -> int | None:
    match = re.search(r"(?:hang excel|excel row|dong excel)\s*(\d+)", q)
    return int(match.group(1)) if match else None


def _data_row_index(q: str) -> int | None:
    if any(term in q for term in ["ban ghi dau tien sau header", "dong du lieu dau tien", "first normalized record"]):
        return 1
    match = re.search(r"(?:dong du lieu thu|data row)\s*(\d+)", q)
    return int(match.group(1)) if match else None


def _machine_filter(q: str, df: pd.DataFrame, machine_col: str | None) -> str | None:
    if not machine_col or machine_col not in df.columns:
        return None
    values = sorted(str(value) for value in df[machine_col].dropna().unique())
    normalized = {_norm(value): value for value in values}
    for norm_value, original in normalized.items():
        if re.search(rf"\b{re.escape(norm_value)}\b", q):
            return original
    machine_mentions = re.findall(r"(may\s*\d+[a-z]?|flexo\s*\d+|die cut)", q)
    if machine_mentions:
        mention = machine_mentions[0].strip()
        candidates = [original for norm_value, original in normalized.items() if norm_value.startswith(mention) or mention in norm_value]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return "__AMBIGUOUS__"
    return None


def _filter_machine(df: pd.DataFrame, machine_col: str | None, machine: str | None) -> pd.DataFrame:
    if machine and machine_col and machine_col in df.columns:
        return df[df[machine_col] == machine].copy()
    return df.copy()


def _parse_date(q: str, df: pd.DataFrame, start_col: str | None) -> tuple[datetime, datetime, str | None] | None:
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", q)
    if iso:
        year, month, day = map(int, iso.groups())
        start = datetime(year, month, day)
        return start, start + timedelta(days=1), None
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", q)
    if not match:
        match = re.search(r"ngay\s*(\d{1,2})\s*thang\s*(\d{1,2})(?:\s*nam\s*(20\d{2}))?", q)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    assumption = None
    if year is None:
        years = []
        if start_col and start_col in df.columns:
            years = sorted({int(ts.year) for ts in pd.to_datetime(df[start_col], errors="coerce").dropna() if ts.month == month and ts.day == day})
        if len(years) == 1:
            year = years[0]
            assumption = f"Interpreted {day:02d}/{month:02d} as {day:02d}/{month:02d}/{year} based on selected file."
        else:
            return None
    start = datetime(year, month, day)
    return start, start + timedelta(days=1), assumption


def _time_window(q: str, day_start: datetime) -> tuple[datetime, datetime] | None:
    match = re.search(r"(?:tu|from)?\s*(\d{1,2})(?:h|:00)?\s*(?:den|-|to)\s*(\d{1,2})(?:h|:00)?", q)
    if not match:
        return None
    h1, h2 = int(match.group(1)), int(match.group(2))
    return datetime.combine(day_start.date(), time(h1, 0)), datetime.combine(day_start.date(), time(h2, 0))


def _instant(q: str, day_start: datetime) -> datetime | None:
    match = re.search(r"(?:luc|at)\s*(\d{1,2})(?::(\d{2}))?", q)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    return datetime.combine(day_start.date(), time(hour, minute))


def _interval_overlap(df: pd.DataFrame, start_col: str, end_col: str, start: datetime, end: datetime) -> pd.DataFrame:
    return df[(df[start_col] < end) & (df[end_col] >= start)].copy()


def _asks_operating_time(q: str) -> bool:
    return any(term in q for term in ["hoat dong", "chay lien tuc", "chay luc nao", "operating"])


def _asks_latest_record(q: str) -> bool:
    if any(term in q for term in ["top", "tong", "theo", "hien thi them", "so lan", "dem", "bao nhieu"]):
        return False
    return any(term in q for term in ["ban ghi", "record", "event", "su kien", "dong"])


def _asks_duplicate_quality(q: str) -> bool:
    return any(term in q for term in ["duplicate", "trung lap", "record trung", "ban ghi trung", "co record trung"])


def _machine_clarification(conversation_id: str, state, debug: bool, started: float) -> ChatResponse:
    return _simple(conversation_id, "clarification", "Can lam ro may", "Ten may bi mo ho. Vui long chon chinh xac, vi co the co May 3 va May 3A.", "CLARIFICATION", state, debug, started, {"generated_sql": None})


def _format_seconds(seconds: float) -> str:
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} day")
    if hours:
        parts.append(f"{hours} hour")
    if minutes:
        parts.append(f"{minutes} minute")
    if secs or not parts:
        parts.append(f"{secs} second")
    return " ".join(parts)


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower().replace("đ", "d").replace("Đ", "d"))
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()
