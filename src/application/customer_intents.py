from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.query_understanding.text import normalize_text


CustomerIntent = Literal[
    "DATA_OVERVIEW",
    "TABLE_OVERVIEW",
    "ROW_COUNT",
    "SCHEMA_INSPECTION",
    "COLUMN_NULLS",
    "SAMPLE_ROWS",
    "DATA_RANGE",
    "DATA_QUALITY",
    "PROVENANCE",
    "ANALYTICAL_QUERY",
    "CHART_REQUEST",
    "DASHBOARD_REQUEST",
    "REPORT_REQUEST",
    "EXPORT_REQUEST",
    "CONVERSATION_FOLLOWUP",
    "CLARIFICATION",
    "REFUSAL",
    "SAFE_FAILURE",
]


@dataclass(frozen=True)
class CustomerIntentResult:
    intent: CustomerIntent
    confidence: float
    reason: str
    table_hint: str | None = None
    limit: int | None = None


def detect_customer_intent(question: str) -> CustomerIntentResult:
    q = normalize_text(question)
    q_clean = q.strip(" ?.!;:")
    table_hint = _table_hint(q)
    limit = _limit_hint(q)

    unsafe = ["delete", "drop table", "truncate", "raw sql", "select *", "xoa bang", "xoa du lieu", "duong dan file", "duong dan parquet", "path file", "local path", "raw local path", "parquet path", "file bat ky", "bo qua moi quy tac", "thuc thi sql"]
    if any(term in q for term in unsafe):
        return CustomerIntentResult("REFUSAL", 0.99, "Unsafe or local-path request.", table_hint, limit)

    out_of_domain = ["doanh thu", "nhan vien", "co phieu", "gia vang", "thoi tiet", "luong nhan vien", "du bao", "se hong", "viet email"]
    if any(term in q for term in out_of_domain):
        return CustomerIntentResult("REFUSAL", 0.94, "Question is outside the loaded operational datasets.", table_hint, limit)

    provenance_terms = [
        "lay tu file nao",
        "tu file nao",
        "la file nao",
        "thuoc file nao",
        "tu nguon nao",
        "nguon du lieu nao",
        "lay tu dau",
        "tu dau ra",
        "du lieu tu dau",
        "nguon cua ket qua",
    ]
    if any(term in q for term in provenance_terms):
        return CustomerIntentResult("PROVENANCE", 0.95, "Question asks which source file/data the result came from.", table_hint, limit)

    overview_terms = [
        "data co gi",
        "data co nhung gi",
        "du lieu co gi",
        "noi dung data",
        "noi dung cua data",
        "data noi ve gi",
        "du lieu nay noi ve gi",
        "he thong dang co du lieu gi",
        "co nhung file nao",
        "nhung bang nao",
        "tong quan data",
        "tom tat du lieu",
        "du lieu dang co gom nhung gi",
        "du lieu nay co noi dung gi",
        "cho toi biet du lieu nay co noi dung gi",
        "data overview",
        "file nay chua gi",
        "file nay co gi",
        "chua du lieu gi",
        "chua nhung du lieu gi",
        "chua nhung gi",
        "chua thong tin gi",
        "du lieu gi",
        "noi dung gi",
        "thong tin gi",
        "gom nhung gi",
        "co nhung gi",
        "chua noi dung gi",
    ]
    if any(term in q for term in overview_terms) or q_clean in {"data", "co gi"}:
        return CustomerIntentResult("DATA_OVERVIEW", 0.98, "Question asks for data/catalog overview.", table_hint, limit)

    row_count_terms = [
        "bao nhieu ban ghi",
        "bao nhieu dong",
        "bao nhieu giao dich",
        "bao nhieu records",
        "bao nhieu dong du lieu",
        "tong so ban ghi",
        "tong so dong",
        "so luong ban ghi",
        "so luong dong",
        "co bao nhieu ban ghi",
        "co bao nhieu dong",
    ]
    if any(term in q for term in row_count_terms) and "khac nhau" not in q:
        return CustomerIntentResult("ROW_COUNT", 0.96, "Question asks for total record count.", table_hint, limit)

    null_column_terms = ["null", "trong", "rong", "thieu", "khuyet", "bo trong"]
    if "cot nao" in q and any(term in q for term in null_column_terms):
        return CustomerIntentResult("COLUMN_NULLS", 0.95, "Question asks which column has the most missing values.", table_hint, limit)

    schema_terms = [
        "schema",
        "cot nao",
        "nhung cot nao",
        "danh sach cot",
        "kieu du lieu",
        "column",
        "columns",
        "cot thoi gian",
        "cot nao la so",
        "cot nao co the join",
        "join duoc bang nao",
        "bang nao chua",
        "file nao nhieu dong",
        "bang nao nhieu dong",
    ]
    if any(term in q for term in schema_terms):
        return CustomerIntentResult("SCHEMA_INSPECTION", 0.96, "Question asks for columns/schema metadata.", table_hint, limit)

    sample_terms = [
        "dong dau",
        "d?ng dau",
        "ban ghi mau",
        "ban ghi m?u",
        "du lieu mau",
        "du lieu m?u",
        "xem thu",
        "sample",
        "preview",
        "hien thi vai",
        "cho vai dong",
        "dong mau",
        "d?ng m?u",
    ]
    if any(term in q for term in sample_terms):
        return CustomerIntentResult("SAMPLE_ROWS", 0.95, "Question asks for sample rows.", table_hint, limit or 5)

    quality_terms = [
        "null", "missing", "thieu du lieu", "duplicate", "dong trung", "ban ghi trung", "trung ban ghi",
        "duration am", "ket thuc truoc", "data quality", "chat luong du lieu",
        "du lieu trong", "gia tri trong", "o trong", "bi trong", "de trong", "con trong", "cot trong", "dong trong",
        "trong khong", "trung lap", "bi trung", "trung nhau", "hoac trung", "co trung", "lap lai",
    ]
    analytical_anomaly = "bat thuong" in q and any(
        term in q
        for term in ["phan tich", "tom tat", "bang", "nhan xet", "insight", "may nao", "downtime", "thoi gian", "theo may"]
    )
    if any(term in q for term in quality_terms) or ("bat thuong" in q and not analytical_anomaly):
        return CustomerIntentResult("DATA_QUALITY", 0.93, "Question asks for data quality checks.", table_hint, limit)

    range_terms = ["tu ngay nao den ngay nao", "du lieu tu ngay nao", "tu ngay nao", "khoang ngay", "thang nao co trong data", "range", "data range"]
    if any(term in q for term in range_terms):
        return CustomerIntentResult("DATA_RANGE", 0.92, "Question asks for dataset ranges/cardinality.", table_hint, limit)

    if table_hint and any(term in q for term in ["chua gi", "noi dung gi", "dung de lam gi", "co noi dung gi"]):
        return CustomerIntentResult("TABLE_OVERVIEW", 0.95, "Question asks for one table overview.", table_hint, limit)

    if any(term in q for term in ["ve", "bieu do", "chart", "plot"]):
        return CustomerIntentResult("CHART_REQUEST", 0.80, "Chart request.", table_hint, limit)
    if any(term in q for term in ["dashboard", "tong quan"]):
        return CustomerIntentResult("DASHBOARD_REQUEST", 0.80, "Dashboard request.", table_hint, limit)
    if any(term in q for term in ["bao cao", "report", "xuat", "excel", "html"]):
        return CustomerIntentResult("REPORT_REQUEST", 0.80, "Report/export request.", table_hint, limit)

    ambiguous_short = {"top may", "may dong", "thang nao", "cai nao cao nhat", "cao nhat", "xem data", "top"}
    if q_clean in ambiguous_short:
        return CustomerIntentResult("CLARIFICATION", 0.90, "Short question lacks metric/table intent.", table_hint, limit)

    return CustomerIntentResult("ANALYTICAL_QUERY", 0.50, "No metadata intent detected.", table_hint, limit)


def _table_hint(q: str) -> str | None:
    if any(term in q for term in ["machine downtime", "downtime", "may dung", "dung may"]):
        return "machine_downtime"
    if any(term in q for term in ["loss assignment", "loss", "ton that", "nguyen nhan"]):
        return "loss_assignment"
    if any(term in q for term in ["entry transaction", "entry", "transaction", "ra vao", "cong", "bien so"]):
        return "entrytransaction"
    return None


def _limit_hint(q: str) -> int | None:
    import re

    match = re.search(r"(\d{1,2})\s*(dong|d.ng|ban ghi|rows?)", q)
    if match:
        return max(1, min(int(match.group(1)), 50))
    match = re.search(r"(top|first|dau)\s*(\d{1,2})", q)
    if match:
        return max(1, min(int(match.group(2)), 50))
    return None
