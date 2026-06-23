from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

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
    table = (catalog.get("tables") or [None])[0]
    if not table:
        return None
    path = _resolve_parquet_path(table.get("parquet_path") or table.get("cache_path"))
    if not path:
        return None
    df = pd.read_parquet(path)
    business_cols = [col["normalized_name"] for col in table.get("columns", []) if not str(col.get("normalized_name", "")).startswith("_")]
    row_count = int(len(df))
    facts: list[AllowedNumericFact] = [AllowedNumericFact("row_count", float(row_count), format_vn_number(row_count, 0))]
    insights: list[InsightCandidate] = []
    rows: list[dict[str, Any]] = []
    limitations = [
        "Kết luận chỉ phản ánh file Excel đang chọn, không tự suy ra nguyên nhân vận hành ngoài dữ liệu.",
        "Các so sánh dựa trên dữ liệu đã import và các cột có sẵn trong file.",
    ]
    duration = _role_column(table, "duration_seconds")
    machine = _role_column(table, "machine")
    loss_group = _role_column(table, "loss_group")
    loss_name = _role_column(table, "loss_name")
    if business_cols and not duration:
        completeness = df[business_cols].notna().mean().sort_values(ascending=False)
        best_col = str(completeness.index[0])
        pct = float(completeness.iloc[0] * 100)
        facts.append(AllowedNumericFact("best_completeness_pct", pct, f"{format_vn_number(pct, 1)}%"))
        insights.append(
            InsightCandidate(
                "Độ đầy đủ dữ liệu",
                f"Cột {humanize_column_name(best_col, catalog)} có tỷ lệ dữ liệu hiện diện cao nhất trong nhóm cột nghiệp vụ.",
                (facts[-1],),
            )
        )
    if duration and duration in df.columns:
        total_seconds = float(pd.to_numeric(df[duration], errors="coerce").fillna(0).sum())
        facts.append(AllowedNumericFact("total_duration_hours", total_seconds / 3600, format_duration(total_seconds)["primary"]))
        insights.append(
            InsightCandidate(
                "Quy mô downtime",
                f"Tổng downtime trong file là {format_duration(total_seconds)['primary']} trên {format_vn_number(row_count, 0)} bản ghi.",
                (facts[-1], facts[0]),
            )
        )
        for role_name, column, label in [
            ("machine", machine, "máy"),
            ("loss_group", loss_group, "nhóm tổn thất"),
            ("loss_name", loss_name, "nguyên nhân tổn thất"),
        ]:
            if not column or column not in df.columns:
                continue
            grouped = (
                df.assign(_duration=pd.to_numeric(df[duration], errors="coerce").fillna(0))
                .groupby(column, dropna=False)
                .agg(total_duration_seconds=("_duration", "sum"), row_count=("_duration", "size"), avg_duration_seconds=("_duration", "mean"))
                .sort_values("total_duration_seconds", ascending=False)
                .head(3)
                .reset_index()
            )
            if grouped.empty:
                continue
            top = grouped.iloc[0]
            total_display = format_duration(top["total_duration_seconds"])["primary"]
            count_display = format_vn_number(top["row_count"], 0)
            avg_display = format_duration(top["avg_duration_seconds"])["primary"]
            f_total = AllowedNumericFact(f"{role_name}_top_total", float(top["total_duration_seconds"]) / 3600, total_display)
            f_count = AllowedNumericFact(f"{role_name}_top_count", float(top["row_count"]), count_display)
            f_avg = AllowedNumericFact(f"{role_name}_top_avg", float(top["avg_duration_seconds"]) / 3600, avg_display)
            label_value = str(top[column])
            label_number = _parse_number(label_value)
            if label_number is not None:
                facts.append(AllowedNumericFact(f"{role_name}_top_label_number", label_number, str(int(label_number) if label_number.is_integer() else label_number)))
            facts.extend([f_total, f_count, f_avg])
            insights.append(
                InsightCandidate(
                    f"Điểm nổi bật theo {label}",
                    f"{label_value} đứng đầu theo tổng downtime với {total_display}, gồm {count_display} lần ghi nhận và trung bình {avg_display} mỗi lần.",
                    (f_total, f_count, f_avg),
                )
            )
            rows.append(
                {
                    "Góc nhìn": humanize_column_name(column, catalog),
                    "Đứng đầu": label_value,
                    "Tổng downtime": total_display,
                    "Số lần ghi nhận": count_display,
                    "Trung bình mỗi lần": avg_display,
                }
            )
    elif business_cols:
        column = business_cols[0]
        grouped = df.groupby(column, dropna=False).size().sort_values(ascending=False).head(3)
        if not grouped.empty:
            top_label = str(grouped.index[0])
            top_count = int(grouped.iloc[0])
            pct = top_count / row_count * 100 if row_count else 0.0
            f_count = AllowedNumericFact("top_count", float(top_count), format_vn_number(top_count, 0))
            f_pct = AllowedNumericFact("top_pct", float(pct), f"{format_vn_number(pct, 1)}%")
            facts.extend([f_count, f_pct])
            insights.append(
                InsightCandidate(
                    "Nhóm xuất hiện nhiều nhất",
                    f"{top_label} xuất hiện nhiều nhất với {format_vn_number(top_count, 0)} bản ghi, chiếm {format_vn_number(pct, 1)}%.",
                    (f_count, f_pct),
                )
            )
            rows.append({"Góc nhìn": humanize_column_name(column, catalog), "Đứng đầu": top_label, "Số lần ghi nhận": format_vn_number(top_count, 0), "Tỷ lệ": f"{format_vn_number(pct, 1)}%"})
    selected = tuple(insights[:4])
    if not selected:
        selected = (InsightCandidate("Quy mô dữ liệu", f"File có {format_vn_number(row_count, 0)} bản ghi có thể truy vấn.", (facts[0],)),)
    comparison = tuple(insight.statement for insight in selected[:3])
    return AnswerBrief(
        source_file_name=source_file_name or _source_file_name(table),
        row_count=row_count,
        selected_insights=selected,
        comparison_facts=comparison,
        limitations=tuple(limitations),
        table_rows=tuple(rows[:5]),
        allowed_numeric_facts=tuple(facts),
    )


def deterministic_open_ended_answer(brief: AnswerBrief) -> str:
    insights = list(brief.selected_insights[:3])
    lines = ["Ba điểm đáng chú ý nhất:"]
    lines.extend(f"- {item.statement}" for item in insights)
    if len(insights) >= 2:
        lines.append("So sánh:")
        lines.append("- Điểm khác biệt chính là mỗi góc nhìn đo một lát cắt khác nhau của file đang chọn: quy mô tổng thể, nhóm đứng đầu và mức lặp lại/trung bình.")
    lines.append("Giới hạn:")
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
    }


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
