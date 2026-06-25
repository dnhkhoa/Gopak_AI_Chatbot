from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.application.overview_analysis import (
    OverviewAnswerBrief,
    build_domain_aware_overview,
    response_quality_errors,
    validate_overview_brief,
)
from src.rendering.formatters import format_duration, format_vn_number, humanize_column_name


@dataclass(frozen=True)
class AllowedNumericFact:
    key: str
    value: float
    display: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class InsightCandidate:
    title: str
    statement: str
    facts: tuple[AllowedNumericFact, ...] = ()


@dataclass(frozen=True)
class AnswerBrief:
    source_file_name: str
    row_count: int
    selected_insights: tuple[InsightCandidate, ...]
    comparison_facts: tuple[str, ...]
    limitations: tuple[str, ...]
    table_rows: tuple[dict[str, Any], ...] = ()
    allowed_numeric_facts: tuple[AllowedNumericFact, ...] = ()
    overview: dict[str, Any] | None = None
    quality_validation: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)


class GroundedComposerValidator:
    def __init__(self, facts: list[AllowedNumericFact] | tuple[AllowedNumericFact, ...]):
        self.facts = list(facts)
        self.allowed_values = [fact.value for fact in self.facts if math.isfinite(fact.value)]
        self.allowed_displays = {
            _normalize_numeric_text(item)
            for fact in self.facts
            for item in (fact.display, *fact.aliases)
            if str(item).strip()
        }
        for fact in self.facts:
            for item in (fact.display, *fact.aliases):
                for raw, _ in _extract_numeric_mentions(str(item)):
                    self.allowed_displays.add(_normalize_numeric_text(raw))

    def validate(self, text: str) -> ValidationResult:
        errors: list[str] = []
        normalized = _ascii(text)
        for term in [
            "context json",
            "answerbrief",
            "planner",
            "structured output",
            "fallback",
            "llm",
            "null",
        ]:
            if term in normalized:
                errors.append(f"internal_term:{term}")
        for phrase in [
            "gan mot nua",
            "mot nua",
            "mot phan",
            "phan nam",
            "gap doi",
            "gap ba",
            "nghiem trong",
            "bat thuong",
            "tuong duong",
            "toan bo",
            "khoang ",
        ]:
            if phrase in normalized:
                errors.append(f"unsupported_claim:{phrase}")
        for phrase in [
            "moi goc nhin do mot lat cat khac nhau",
            "du lieu cho thay nhieu thong tin huu ich",
            "ket qua co the ho tro ra quyet dinh",
            "can xem xet them de co ket luan chinh xac",
        ]:
            if phrase in normalized:
                errors.append(f"generic_filler:{phrase}")
        for raw, value in _extract_numeric_mentions(text):
            if not self._is_allowed(raw, value):
                errors.append(f"unsupported_number:{raw}")
        return ValidationResult(passed=not errors, errors=errors)

    def _is_allowed(self, raw: str, value: float) -> bool:
        normalized = _normalize_numeric_text(raw)
        if normalized in self.allowed_displays:
            return True
        return any(abs(value - allowed) <= max(0.01, abs(allowed) * 0.0005) for allowed in self.allowed_values)


def build_fact_registry_from_table(table: Any, requested_top_n: int | None = None) -> list[AllowedNumericFact]:
    if not table:
        return []
    rows = getattr(table, "rows", None) or []
    columns = getattr(table, "columns", None) or []
    facts: list[AllowedNumericFact] = []
    if requested_top_n:
        facts.append(AllowedNumericFact("requested_top_n", float(requested_top_n), str(requested_top_n)))
    facts.append(AllowedNumericFact("displayed_row_count", float(len(rows)), str(len(rows))))
    for row_index, row in enumerate(rows, start=1):
        facts.append(AllowedNumericFact(f"rank_{row_index}", float(row_index), str(row_index)))
        for column in columns:
            value = row.get(column)
            number = _parse_number(value)
            if number is None:
                continue
            display = str(value)
            aliases = [display.replace("%", "").strip()] if "%" in display else []
            aliases.extend(raw for raw, _ in _extract_numeric_mentions(display))
            facts.append(
                AllowedNumericFact(
                    key=f"r{row_index}.{column}",
                    value=number,
                    display=display,
                    aliases=tuple(alias for alias in aliases if alias),
                )
            )
    return facts


def deterministic_table_commentary(message: str, response: Any) -> str:
    table = response.table
    if not table or not table.rows:
        return ""
    rows = table.rows
    columns = table.columns
    dim_col = _dimension_column(columns, rows)
    numeric_cols = [col for col in columns if col != dim_col and any(_parse_number(row.get(col)) is not None for row in rows)]
    if not dim_col or not numeric_cols:
        return ""
    q = _ascii(message)
    first = rows[0]
    top_label = str(first.get(dim_col))
    main_col = numeric_cols[0]
    lines = [f"- {top_label} đứng đầu trong bảng với {first.get(main_col)} ở chỉ tiêu {main_col.lower()}."]
    if len(rows) >= 2:
        second = rows[1]
        second_label = str(second.get(dim_col))
        lines.append(f"- {second_label} đứng thứ hai với {second.get(main_col)}, nên nhóm đầu bảng có chênh lệch rõ khi so với hàng kế tiếp.")
    if len(numeric_cols) >= 2:
        extra_parts = [f"{col.lower()} {first.get(col)}" for col in numeric_cols[1:3]]
        if extra_parts:
            lines.append(f"- Với {top_label}, các chỉ tiêu bổ sung là " + " và ".join(extra_parts) + ".")
    if "phan tram" in q or "ty le" in q or "ty trong" in q:
        percent_col = next((col for col in numeric_cols if "%" in str(first.get(col)) or "tỷ lệ" in _ascii(col) or "percentage" in _ascii(col)), None)
        if percent_col:
            lines.append(f"- Tỷ lệ của {top_label} là {first.get(percent_col)} trong phạm vi các dòng đang hiển thị.")
    requested = _requested_top_n(q)
    if requested and len(rows) < requested:
        lines.append(f"- Bảng chỉ có {len(rows)} dòng kết quả, thấp hơn top {requested} được yêu cầu.")
    return "Nhận xét:\n" + "\n".join(lines[:4])


def build_open_ended_answer_brief(catalog: dict, source_file_name: str = "") -> AnswerBrief | None:
    overview = build_domain_aware_overview(catalog, source_file_name)
    if overview is not None:
        return _answer_brief_from_overview(overview)
    table = (catalog.get("tables") or [None])[0]
    if not table:
        return None
    path = _resolve_parquet_path(table.get("parquet_path") or table.get("cache_path"))
    if not path:
        return None
    df = pd.read_parquet(path)
    row_count = int(len(df))
    fact = AllowedNumericFact("row_count", float(row_count), format_vn_number(row_count, 0))
    return AnswerBrief(
        source_file_name=source_file_name or _source_file_name(table),
        row_count=row_count,
        selected_insights=(
            InsightCandidate(
                "Chua du tin hieu nghiep vu",
                "Toi chua xac dinh duoc phat hien nghiep vu du tin cay tu du lieu hien tai; cac cot con lai chua du khac biet hoac chua du y nghia tong hop de ket luan.",
                (fact,),
            ),
        ),
        comparison_facts=(),
        limitations=("Ket qua chi phan anh file dang chon va khong tao insight neu cot khong du y nghia nghiep vu.",),
        table_rows=(),
        allowed_numeric_facts=(fact,),
        quality_validation={"passed": False, "errors": ["insufficient_business_columns"]},
    )


def deterministic_open_ended_answer(brief: AnswerBrief) -> str:
    insights = list(brief.selected_insights[:3])
    dataset = ""
    if brief.overview and brief.overview.get("dataset_description"):
        dataset = str(brief.overview["dataset_description"])
    lines = ["Tổng quan dữ liệu"]
    if dataset:
        lines.append(dataset)
    lines.append("")
    lines.append("Các phát hiện đáng chú ý")
    if insights:
        lines.extend(f"- {item.statement}" for item in insights)
    else:
        lines.append("Tôi chưa xác định được phát hiện nghiệp vụ đủ tin cậy từ các cột hiện tại.")
    if len(insights) >= 2:
        lines.append("")
        lines.append("So sánh")
        lines.append(f"{insights[0].title} và {insights[1].title} dùng hai chỉ số khác nhau; nên xem riêng mức độ đóng góp và tần suất/phân bố.")
    lines.append("")
    lines.append("Giới hạn")
    lines.extend(f"- {item}" for item in brief.limitations[:2])
    return "\n".join(lines)


def brief_to_prompt_payload(brief: AnswerBrief) -> dict[str, Any]:
    return {
        "source_file_name": brief.source_file_name,
        "row_count": brief.row_count,
        "selected_insights": [item.__dict__ | {"facts": [fact.__dict__ for fact in item.facts]} for item in brief.selected_insights],
        "comparison_facts": list(brief.comparison_facts),
        "limitations": list(brief.limitations),
        "table_rows": list(brief.table_rows),
        "allowed_numbers": [fact.__dict__ for fact in brief.allowed_numeric_facts],
        "overview": brief.overview or {},
        "quality_validation": brief.quality_validation or {},
    }


def _answer_brief_from_overview(overview: OverviewAnswerBrief) -> AnswerBrief:
    facts: list[AllowedNumericFact] = [
        AllowedNumericFact("record_count", float(overview.record_count), format_vn_number(overview.record_count, 0)),
        AllowedNumericFact("column_count", float(overview.column_count), format_vn_number(overview.column_count, 0)),
    ]
    if overview.date_range:
        for key in ("start", "end"):
            raw_date = str(overview.date_range.get(key) or "")
            for raw, value in _extract_numeric_mentions(raw_date):
                facts.append(AllowedNumericFact(f"date_{key}_{raw}", value, raw))
    insights: list[InsightCandidate] = []
    for insight in overview.selected_insights:
        insight_facts: list[AllowedNumericFact] = []
        if insight.primary_entity:
            for raw, value in _extract_numeric_mentions(str(insight.primary_entity)):
                facts.append(AllowedNumericFact(f"{insight.insight_id}_entity_{raw}", value, raw))
        for raw_fact in insight.facts:
            try:
                value = float(raw_fact.get("value"))
            except Exception:
                continue
            display = str(raw_fact.get("display") or value)
            fact = AllowedNumericFact(str(raw_fact.get("key") or insight.insight_id), value, display)
            facts.append(fact)
            insight_facts.append(fact)
        insights.append(InsightCandidate(insight.title, insight.statement, tuple(insight_facts)))
    rows = tuple((overview.supporting_table or {}).get("rows") or [])
    validation = validate_overview_brief(overview)
    validation_errors = list(validation.get("errors") or [])
    validation_errors.extend(response_quality_errors(" ".join(item.statement for item in overview.selected_insights)))
    quality_validation = {**validation, "errors": validation_errors, "passed": not validation_errors}
    if not insights:
        message = "Toi chua xac dinh duoc phat hien nghiep vu du tin cay tu du lieu hien tai. Cac cot con lai chua du khac biet hoac chua du y nghia tong hop de ket luan."
        insights.append(InsightCandidate("Chua du tin hieu nghiep vu", message, tuple(facts[:1])))
    return AnswerBrief(
        source_file_name=overview.source_file_name,
        row_count=overview.record_count,
        selected_insights=tuple(insights),
        comparison_facts=tuple(item.get("fact", "") for item in overview.comparison_facts if item.get("fact")),
        limitations=tuple(overview.limitations),
        table_rows=rows,
        allowed_numeric_facts=tuple(facts),
        overview=overview.model_dump(),
        quality_validation=quality_validation,
    )

def json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _dimension_column(columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    for column in columns:
        if any(_parse_number(row.get(column)) is None for row in rows[:3]):
            return column
    return columns[0] if columns else None


def _requested_top_n(normalized_question: str) -> int | None:
    match = re.search(r"top\s*(\d{1,2})", normalized_question)
    return int(match.group(1)) if match else None


def _extract_numeric_mentions(text: str) -> list[tuple[str, float]]:
    mentions: list[tuple[str, float]] = []
    pattern = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?:\s*%)?")
    for match in pattern.finditer(text):
        raw = match.group(0).strip()
        value = _parse_number(raw)
        if value is not None:
            mentions.append((raw, value))
    return mentions


def _parse_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\d+(?:[.,]\d+)*", text)
    if not match:
        return None
    token = match.group(0)
    if "," in token:
        token = token.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def _normalize_numeric_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _ascii(text: str) -> str:
    lowered = str(text).lower().replace("đ", "d").replace("Đ", "d")
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _resolve_parquet_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.exists():
        return path
    candidate = Path.cwd() / str(value)
    return candidate if candidate.exists() else None


def _role_column(table: dict, role: str) -> str | None:
    for column in table.get("columns", []):
        if column.get("semantic_role") == role:
            return str(column.get("normalized_name") or "")
    return None


def _source_file_name(table: dict) -> str:
    source = str(table.get("source") or table.get("source_file") or "")
    return Path(source.split(" / ", 1)[0]).name
