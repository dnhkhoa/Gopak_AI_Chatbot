"""Public response sanitizer + validators.

Every response passes through this egress gate before it is persisted or returned
to the browser. The gate repairs customer-facing labels, blocks metadata leakage,
and rejects junk narratives such as a one-character ``D``.
"""
from __future__ import annotations

import re
from typing import Any

from src.rendering.labels import display_label, find_internal_keys, find_unaccented_vietnamese


_TEXT_FIELDS = ("title", "summary", "primary_value", "secondary_value")
_INVALID_NARRATIVE_VALUES = {"d", "ok", "none", "null", "-", "..."}
_SAFE_FALLBACK_SUMMARY = "Kết quả đã được tổng hợp từ file đang chọn."


def is_valid_customer_narrative(text: str | None) -> bool:
    if text is None:
        return False
    value = str(text).strip()
    if len(value) < 12:
        return False
    if value.lower() in _INVALID_NARRATIVE_VALUES:
        return False
    if not any(char.isalpha() for char in value):
        return False
    if re.fullmatch(r"[\W_]+", value, flags=re.UNICODE):
        return False
    return bool(re.search(r"\s", value) or any(mark in value for mark in ".:;,-–"))


def _iter_label_strings(response: Any) -> list[str]:
    out: list[str] = []
    table = getattr(response, "table", None)
    if table is not None:
        out.extend(str(c) for c in (table.columns or []))
    chart = getattr(response, "chart", None)
    if chart is not None and getattr(chart, "title", None):
        out.append(str(chart.title))
    dashboard = getattr(response, "dashboard", None)
    if dashboard is not None:
        nested_table = getattr(dashboard, "table", None)
        if nested_table is not None:
            out.extend(str(c) for c in (nested_table.columns or []))
        nested_chart = getattr(dashboard, "chart", None)
        if nested_chart is not None and getattr(nested_chart, "title", None):
            out.append(str(nested_chart.title))
    report = getattr(response, "report", None)
    if report is not None:
        for section in getattr(report, "sections", []) or []:
            if getattr(section, "table", None) is not None:
                out.extend(str(c) for c in (section.table.columns or []))
            if getattr(section, "chart", None) is not None and getattr(section.chart, "title", None):
                out.append(str(section.chart.title))
    for item in getattr(response, "filters", []) or []:
        if getattr(item, "label", None):
            out.append(str(item.label))
    return out


def scan_response(response: Any) -> dict[str, Any]:
    internal_keys: list[str] = []
    unaccented: list[str] = []
    for field in _TEXT_FIELDS:
        value = getattr(response, field, None)
        if isinstance(value, str) and value:
            internal_keys.extend(find_internal_keys(value))
            unaccented.extend(find_unaccented_vietnamese(value))
    for label in _iter_label_strings(response):
        internal_keys.extend(find_internal_keys(label))
        unaccented.extend(find_unaccented_vietnamese(label))
    return {
        "internal_keys": sorted(set(internal_keys)),
        "unaccented_vietnamese": sorted(set(unaccented)),
        "clean": not internal_keys and not unaccented,
    }


def scan_narrative_quality(response: Any) -> dict[str, Any]:
    invalid: list[dict[str, str]] = []

    def check(path: str, value: Any, *, optional: bool = True) -> None:
        if value is None:
            return
        text = str(value)
        if optional and not text.strip():
            return
        if not is_valid_customer_narrative(text):
            invalid.append({"path": path, "value": text})

    check("summary", getattr(response, "summary", None))

    analysis = getattr(response, "analysis", None)
    if analysis is not None:
        check("analysis.headline", getattr(analysis, "headline", None))
        check("analysis.summary", getattr(analysis, "summary", None))
        for idx, insight in enumerate(getattr(analysis, "insights", []) or []):
            check(f"analysis.insights[{idx}].text", getattr(insight, "text", None))

    report = getattr(response, "report", None)
    if report is not None:
        for idx, item in enumerate(getattr(report, "executive_summary", []) or []):
            check(f"report.executive_summary[{idx}]", item)
        for idx, item in enumerate(getattr(report, "limitations", []) or []):
            check(f"report.limitations[{idx}]", item)
        for section_idx, section in enumerate(getattr(report, "sections", []) or []):
            check(f"report.sections[{section_idx}].summary", getattr(section, "summary", None))
            for idx, item in enumerate(getattr(section, "commentary", []) or []):
                check(f"report.sections[{section_idx}].commentary[{idx}]", item)
    return {"invalid": invalid, "clean": not invalid}


class PublicResponseSanitizer:
    def __init__(self, repair: bool = True) -> None:
        self.repair = repair

    def sanitize(self, response: Any) -> Any:
        self._repair_payload_labels(response)

        findings = scan_response(response)
        narrative = scan_narrative_quality(response)
        meta = getattr(response, "metadata", None)
        if isinstance(meta, dict):
            meta["public_response_validation"] = findings
            meta["localization_validation"] = {
                "internal_keys": findings["internal_keys"],
                "unaccented_vietnamese": findings["unaccented_vietnamese"],
                "passed": findings["clean"],
            }
            meta["metadata_leakage_validation"] = {
                "internal_keys": findings["internal_keys"],
                "passed": not findings["internal_keys"],
            }
            meta["narrative_quality_validation"] = narrative

        if self.repair and not findings["clean"]:
            self._repair_text_fields(response)
            self._repair_payload_labels(response)
        if self.repair and not narrative["clean"]:
            self._repair_invalid_narratives(response)

        if isinstance(meta, dict):
            meta["public_response_validation_after_repair"] = scan_response(response)
            meta["narrative_quality_validation_after_repair"] = scan_narrative_quality(response)
        return response

    def _repair_payload_labels(self, response: Any) -> None:
        self._repair_table(getattr(response, "table", None))
        self._repair_chart(getattr(response, "chart", None))
        dashboard = getattr(response, "dashboard", None)
        if dashboard is not None:
            self._repair_table(getattr(dashboard, "table", None))
            self._repair_chart(getattr(dashboard, "chart", None))
        report = getattr(response, "report", None)
        if report is not None:
            for section in getattr(report, "sections", []) or []:
                self._repair_table(getattr(section, "table", None))
                self._repair_chart(getattr(section, "chart", None))

    def _repair_table(self, table: Any) -> None:
        if table is None or not getattr(table, "columns", None):
            return
        old_columns = [str(col) for col in table.columns]
        new_columns = [self._repair_label(col) for col in old_columns]
        if new_columns == old_columns:
            return
        table.columns = new_columns
        if getattr(table, "rows", None):
            renamed_rows = []
            for row in table.rows:
                renamed = dict(row)
                for old, new in zip(old_columns, new_columns):
                    if old in renamed and new not in renamed:
                        renamed[new] = renamed.pop(old)
                renamed_rows.append(renamed)
            table.rows = renamed_rows

    def _repair_chart(self, chart: Any) -> None:
        if chart is None:
            return
        if getattr(chart, "title", None) and find_internal_keys(str(chart.title)):
            chart.title = display_label(str(chart.title))
        if getattr(chart, "x_key", None):
            chart.x_key = self._repair_label(str(chart.x_key))
        if getattr(chart, "y_keys", None):
            chart.y_keys = [self._repair_label(str(item)) for item in chart.y_keys]
        if getattr(chart, "data", None):
            repaired_rows = []
            for row in chart.data:
                repaired_rows.append({self._repair_label(str(key)): value for key, value in dict(row).items()})
            chart.data = repaired_rows

    def _repair_label(self, label: str) -> str:
        text = str(label)
        if find_internal_keys(text) or text.upper() == text:
            return display_label(text)
        return text

    def _repair_text_fields(self, response: Any) -> None:
        for field in _TEXT_FIELDS:
            value = getattr(response, field, None)
            if not isinstance(value, str) or not value:
                continue
            repaired = value
            for key in find_internal_keys(repaired):
                repaired = repaired.replace(key, display_label(key))
            if field == "summary" and find_unaccented_vietnamese(repaired):
                repaired = self._fallback_for_response(response)
            if repaired != value:
                setattr(response, field, repaired)

    def _repair_invalid_narratives(self, response: Any) -> None:
        fallback = self._fallback_for_response(response)
        for field in _TEXT_FIELDS:
            if field == "title":
                continue
            value = getattr(response, field, None)
            if value is not None and str(value).strip() and not is_valid_customer_narrative(str(value)):
                setattr(response, field, fallback if field == "summary" else "")

        analysis = getattr(response, "analysis", None)
        if analysis is not None:
            if getattr(analysis, "headline", None) and not is_valid_customer_narrative(analysis.headline):
                analysis.headline = "Phân tích dữ liệu"
            if getattr(analysis, "summary", None) and not is_valid_customer_narrative(analysis.summary):
                analysis.summary = fallback
            for insight in getattr(analysis, "insights", []) or []:
                if getattr(insight, "text", None) and not is_valid_customer_narrative(insight.text):
                    insight.text = fallback

        report = getattr(response, "report", None)
        if report is not None:
            report.executive_summary = [item for item in report.executive_summary if is_valid_customer_narrative(item)]
            report.limitations = [item for item in report.limitations if is_valid_customer_narrative(item)]
            for section in report.sections:
                if section.summary and not is_valid_customer_narrative(section.summary):
                    section.summary = None
                section.commentary = [item for item in section.commentary if is_valid_customer_narrative(item)]

    def _fallback_for_response(self, response: Any) -> str:
        report = getattr(response, "report", None)
        if report is not None:
            for item in getattr(report, "executive_summary", []) or []:
                if is_valid_customer_narrative(item):
                    return str(item)
        analysis = getattr(response, "analysis", None)
        if analysis is not None:
            if is_valid_customer_narrative(getattr(analysis, "summary", None)):
                return str(analysis.summary)
            for insight in getattr(analysis, "insights", []) or []:
                if is_valid_customer_narrative(getattr(insight, "text", None)):
                    return str(insight.text)
        table = getattr(response, "table", None)
        if table is not None and getattr(table, "rows", None):
            return f"Kết quả gồm {len(table.rows)} dòng dữ liệu đã được tính từ file đang chọn."
        return _SAFE_FALLBACK_SUMMARY
