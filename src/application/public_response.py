"""Public response gateway.

All customer-facing responses pass through this module before they are returned
by the API. The gateway localizes labels, formats dates/numbers for Vietnamese
readers, removes internal keys, and records validation findings in metadata for
debugging without exposing raw internals to the UI.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from src.rendering.labels import display_label, find_internal_keys, find_unaccented_vietnamese


_TEXT_FIELDS = ("title", "summary", "primary_value", "secondary_value")
_INVALID_NARRATIVE_VALUES = {"d", "ok", "none", "null", "-", "..."}
_SAFE_FALLBACK_SUMMARY = "Kết quả đã được tổng hợp từ nguồn dữ liệu hiện tại."
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?\b")


PUBLIC_ERROR_MESSAGES = {
    "NO_DATA_IN_RANGE": "Không tìm thấy dữ liệu trong khoảng thời gian được yêu cầu.",
    "DATE_OUTSIDE_DATA_RANGE": "Ngày được chọn nằm ngoài phạm vi dữ liệu hiện có.",
    "SOURCE_NOT_READY": "Nguồn dữ liệu cần thiết hiện chưa sẵn sàng. Vui lòng thử lại sau.",
    "SOURCE_MISSING": "Không tìm thấy nguồn dữ liệu cần thiết để thực hiện yêu cầu này.",
    "UNSUPPORTED_BY_ACTIVE_BUNDLE": "Các nguồn dữ liệu hiện tại chưa hỗ trợ yêu cầu này.",
    "PERFORMANCE_FORMULA_DISABLED": "Hiện chưa thể tính OEE riêng theo ngày vì công thức Performance chính thức chưa được cấu hình.",
    "MODEL_UNAVAILABLE": "Mô hình AI hiện chưa sẵn sàng. Vui lòng kiểm tra dịch vụ Ollama và thử lại.",
    "QUERY_FAILED": "Không thể hoàn tất phép phân tích dữ liệu. Vui lòng thử lại hoặc điều chỉnh yêu cầu.",
    "REPORT_GENERATION_FAILED": "Không thể tạo báo cáo tại thời điểm này. Vui lòng thử lại.",
    "PDF_GENERATION_FAILED": "Không thể tạo file PDF tại thời điểm này. Nội dung báo cáo vẫn được giữ lại.",
    "UNKNOWN_INTERNAL_ERROR": "Đã xảy ra lỗi trong quá trình xử lý. Vui lòng thử lại.",
}

SOURCE_LABELS = {
    "apqoee_cumulative": "APQOEE tích lũy",
    "APQOEE Cumulative": "APQOEE tích lũy",
    "machine_downtime": "Dữ liệu downtime máy",
    "Machine Downtime": "Dữ liệu downtime máy",
    "loss_assignment": "Dữ liệu phân bổ tổn thất",
    "Loss Assignment": "Dữ liệu phân bổ tổn thất",
}

METRIC_LABELS = {
    "Cumulative OEE": "OEE tích lũy",
    "Cumulative Availability": "Availability tích lũy",
    "Cumulative Performance": "Performance tích lũy",
    "Cumulative Quality": "Quality tích lũy",
    "Downtime duration": "Tổng thời lượng downtime",
    "Downtime event count": "Số lần dừng máy",
    "Loss duration": "Tổng thời lượng tổn thất",
    "Loss event count": "Số lần ghi nhận tổn thất",
    "Affected machines": "Số máy bị ảnh hưởng",
    "OEE": "OEE tích lũy",
    "Availability": "Availability tích lũy",
    "Performance": "Performance tích lũy",
    "Quality": "Quality tích lũy",
}

PUBLIC_COLUMN_LABELS = {
    "source_id": "Nguồn dữ liệu",
    "source": "Nguồn dữ liệu",
    "metric": "Chỉ số",
    "value": "Giá trị",
    "unit": "Đơn vị",
    "time_scope": "Phạm vi thời gian",
    "snapshot_time": "Thời điểm snapshot",
    "Source id": "Nguồn dữ liệu",
    "Source": "Nguồn dữ liệu",
    "Time scope": "Phạm vi thời gian",
    "Snapshot time": "Thời điểm snapshot",
    "Date range": "Phạm vi thời gian",
    "Limitations": "Giới hạn phân tích",
    "Sources": "Nguồn dữ liệu",
    "Time scope": "Phạm vi thời gian",
    "Rows": "Số bản ghi",
    "rows": "Số bản ghi",
    "Columns": "Số cột",
    "columns": "Số cột",
    "Grain": "Cấp dữ liệu",
    "grain": "Cấp dữ liệu",
    "Date": "Ngày",
    "date": "Ngày",
    "Date label": "Ngày",
    "date_label": "Ngày",
    "Downtime hours": "Tổng downtime (giờ)",
    "downtime_hours": "Tổng downtime (giờ)",
    "Event count": "Số lần",
    "event_count": "Số lần",
    "Affected machines": "Số máy bị ảnh hưởng",
    "affected_machines": "Số máy bị ảnh hưởng",
    "Baseline date": "Ngày gốc",
    "baseline_date": "Ngày gốc",
    "Baseline value": "Giá trị gốc",
    "baseline_value": "Giá trị gốc",
    "Current date": "Ngày so sánh",
    "current_date": "Ngày so sánh",
    "Current value": "Giá trị so sánh",
    "current_value": "Giá trị so sánh",
    "Delta percentage points": "Chênh lệch (điểm %)",
    "delta_percentage_points": "Chênh lệch (điểm %)",
    "machine": "Máy",
    "loss_group": "Nhóm tổn thất",
}

FORBIDDEN_PUBLIC_TOKENS = {
    "The analysis service could not complete this request",
    "Internal server error",
    "Model timeout",
    "Schema mismatch",
    "ValueError",
    "KeyError",
    "Stack trace",
    "SUCCESS",
    "NaN",
    "None",
    "null",
    "fallback",
    "REAL_LLM",
    "query_plan_id",
    "query_result_id",
    "artifact_id",
    "machine_total_downtime",
    "daily_total_downtime",
    "apqoee_cumulative",
}


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
        for row in getattr(table, "rows", []) or []:
            out.extend(str(key) for key in dict(row).keys())
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
    forbidden: list[str] = []
    chunks: list[str] = []
    for field in _TEXT_FIELDS:
        value = getattr(response, field, None)
        if isinstance(value, str) and value:
            chunks.append(value)
    for label in _iter_label_strings(response):
        chunks.append(label)
    table = getattr(response, "table", None)
    if table is not None:
        for row in getattr(table, "rows", []) or []:
            chunks.extend(str(value) for value in dict(row).values())
    for text in chunks:
        internal_keys.extend(find_internal_keys(text))
        unaccented.extend(find_unaccented_vietnamese(text))
        forbidden.extend(token for token in FORBIDDEN_PUBLIC_TOKENS if token in text)
    return {
        "internal_keys": sorted(set(internal_keys)),
        "unaccented_vietnamese": sorted(set(unaccented)),
        "forbidden_tokens": sorted(set(forbidden)),
        "raw_iso_timestamps": sorted(set(_ISO_RE.findall("\n".join(chunks)))),
        "clean": not internal_keys and not unaccented and not forbidden and not _ISO_RE.findall("\n".join(chunks)),
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
        self._localize_response(response)
        self._repair_payload_labels(response)

        findings = scan_response(response)
        narrative = scan_narrative_quality(response)
        meta = getattr(response, "metadata", None)
        if isinstance(meta, dict):
            meta["public_response_validation"] = findings
            meta["localization_validation"] = {
                "internal_keys": findings["internal_keys"],
                "unaccented_vietnamese": findings["unaccented_vietnamese"],
                "forbidden_tokens": findings["forbidden_tokens"],
                "raw_iso_timestamps": findings["raw_iso_timestamps"],
                "passed": findings["clean"],
            }
            meta["metadata_leakage_validation"] = {
                "internal_keys": findings["internal_keys"],
                "forbidden_tokens": findings["forbidden_tokens"],
                "passed": not findings["internal_keys"] and not findings["forbidden_tokens"],
            }
            meta["narrative_quality_validation"] = narrative

        if self.repair and not findings["clean"]:
            self._repair_text_fields(response)
            self._localize_response(response)
            self._repair_payload_labels(response)
        if self.repair and not narrative["clean"]:
            self._repair_invalid_narratives(response)

        if isinstance(meta, dict):
            meta["public_response_validation_after_repair"] = scan_response(response)
            meta["narrative_quality_validation_after_repair"] = scan_narrative_quality(response)
        return response

    def _localize_response(self, response: Any) -> None:
        self._localize_text_fields(response)
        self._localize_sources(response)
        self._localize_filters(response)
        self._localize_table(getattr(response, "table", None))
        analysis = getattr(response, "analysis", None)
        if analysis is not None:
            if getattr(analysis, "headline", None):
                analysis.headline = _public_text(analysis.headline)
            if getattr(analysis, "summary", None):
                analysis.summary = _public_text(analysis.summary)
            self._localize_table(getattr(analysis, "table", None))
            for insight in getattr(analysis, "insights", []) or []:
                if getattr(insight, "text", None):
                    insight.text = _public_text(insight.text)
                if getattr(insight, "evidence", None):
                    insight.evidence = [_source_label(item) for item in insight.evidence]
        self._localize_chart(getattr(response, "chart", None))
        dashboard = getattr(response, "dashboard", None)
        if dashboard is not None:
            self._localize_table(getattr(dashboard, "table", None))
            self._localize_chart(getattr(dashboard, "chart", None))
        report = getattr(response, "report", None)
        if report is not None:
            report.title = _public_text(report.title)
            if report.subtitle:
                report.subtitle = _public_text(report.subtitle)
            report.executive_summary = [_public_text(item) for item in report.executive_summary]
            report.limitations = [_public_text(item) for item in report.limitations]
            for section in report.sections:
                section.title = _public_text(section.title)
                if section.summary:
                    section.summary = _public_text(section.summary)
                section.commentary = [_public_text(item) for item in section.commentary]
                self._localize_table(getattr(section, "table", None))
                self._localize_chart(getattr(section, "chart", None))

    def _localize_text_fields(self, response: Any) -> None:
        status = ""
        meta = getattr(response, "metadata", None)
        if isinstance(meta, dict):
            status = str(meta.get("status") or "")
        if getattr(response, "response_type", "") in {"error", "refusal"}:
            response.summary = _error_message(status, getattr(response, "summary", ""))
            response.title = _error_title(status)
        for field in _TEXT_FIELDS:
            value = getattr(response, field, None)
            if isinstance(value, str) and value:
                setattr(response, field, _public_text(value))
        if _is_apqoee_table(getattr(response, "table", None)):
            response.title = "APQOEE tích lũy"
            response.summary = _apqoee_summary(response.table.rows)

    def _localize_sources(self, response: Any) -> None:
        for source in getattr(response, "sources", []) or []:
            if getattr(source, "name", None):
                source.name = _source_label(source.name)

    def _localize_filters(self, response: Any) -> None:
        for item in getattr(response, "filters", []) or []:
            if getattr(item, "label", None):
                item.label = _column_label(item.label)
            if getattr(item, "value", None) is not None:
                if isinstance(item.value, list):
                    item.value = ", ".join(_source_label(value) for value in item.value)
                elif isinstance(item.value, str):
                    item.value = _public_text(_source_label(item.value))
            if getattr(item, "operator", None):
                item.operator = {"in": "gồm", "equals": "là"}.get(str(item.operator), str(item.operator))

    def _localize_chart(self, chart: Any) -> None:
        if chart is None:
            return
        if getattr(chart, "title", None):
            chart.title = _public_text(chart.title)
        if getattr(chart, "x_key", None):
            chart.x_key = _column_label(chart.x_key)
        if getattr(chart, "y_keys", None):
            chart.y_keys = [_column_label(item) for item in chart.y_keys]
        if getattr(chart, "tooltip_unit", None):
            chart.tooltip_unit = _unit_label(chart.tooltip_unit)
        if getattr(chart, "x_axis_unit", None):
            chart.x_axis_unit = _unit_label(chart.x_axis_unit)
        if getattr(chart, "y_axis_unit", None):
            chart.y_axis_unit = _unit_label(chart.y_axis_unit)
        if getattr(chart, "data", None):
            chart.data = [_localized_row(row, compact=False) for row in chart.data]

    def _localize_table(self, table: Any) -> None:
        if table is None:
            return
        rows = [dict(row) for row in (getattr(table, "rows", None) or [])]
        if not rows:
            return
        if _is_production_metric_rows(rows):
            table.columns = ["Chỉ số", "Giá trị"]
            table.rows = [_metric_row(row) for row in rows]
            return
        table.rows = [_localized_row(row, compact=True) for row in rows]
        columns: list[str] = []
        for row in table.rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        table.columns = columns

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
            chart.data = [{self._repair_label(str(key)): value for key, value in dict(row).items()} for row in chart.data]

    def _repair_label(self, label: str) -> str:
        text = str(label)
        if text in PUBLIC_COLUMN_LABELS:
            return PUBLIC_COLUMN_LABELS[text]
        if text in SOURCE_LABELS:
            return SOURCE_LABELS[text]
        if text in METRIC_LABELS:
            return METRIC_LABELS[text]
        if find_internal_keys(text) or text.upper() == text:
            return display_label(text)
        return text

    def _repair_text_fields(self, response: Any) -> None:
        for field in _TEXT_FIELDS:
            value = getattr(response, field, None)
            if not isinstance(value, str) or not value:
                continue
            repaired = _public_text(value)
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
        analysis = getattr(response, "analysis", None)
        if analysis is not None:
            if is_valid_customer_narrative(getattr(analysis, "summary", None)):
                return str(analysis.summary)
            for insight in getattr(analysis, "insights", []) or []:
                if is_valid_customer_narrative(getattr(insight, "text", None)):
                    return str(insight.text)
        table = getattr(response, "table", None)
        if table is not None and getattr(table, "rows", None):
            return f"Kết quả gồm {len(table.rows)} dòng dữ liệu đã được tính từ nguồn hiện tại."
        return _SAFE_FALLBACK_SUMMARY


def _error_title(status: str) -> str:
    if status == "PLAN_REJECTED":
        return "Chưa thể thực hiện phép tính này"
    if status == "SAFE_FAILURE":
        return "Yêu cầu chưa thể xử lý"
    return "Không thể hoàn tất yêu cầu"


def _error_message(status: str, summary: Any) -> str:
    text = str(summary or "")
    if "Performance formula" in text or "Period-specific APQOEE" in text or status == "PLAN_REJECTED":
        return (
            "Chưa thể tính OEE riêng theo ngày\n\n"
            "Hiện hệ thống chỉ có giá trị APQOEE tích lũy. Việc tính OEE riêng cho từng ngày cần công thức Performance chính thức và các giá trị chênh lệch của counter/thời gian.\n\n"
            "Hệ thống không sử dụng phép trừ hai giá trị OEE tích lũy vì cách tính đó không chính xác."
        )
    if "BUSINESS_TIMEZONE" in text:
        return "Chưa thể chia ngày hoặc ca vì múi giờ nghiệp vụ chưa được cấu hình."
    if "No APQOEE snapshot" in text:
        return PUBLIC_ERROR_MESSAGES["DATE_OUTSIDE_DATA_RANGE"]
    if "unavailable" in text.lower() or "not ready" in text.lower():
        return PUBLIC_ERROR_MESSAGES["SOURCE_NOT_READY"]
    if "Execution failed" in text or status in {"EXECUTION_FAILED", "SAFE_FAILURE"}:
        return PUBLIC_ERROR_MESSAGES["QUERY_FAILED"]
    if not text.strip() or any(token in text for token in FORBIDDEN_PUBLIC_TOKENS):
        return PUBLIC_ERROR_MESSAGES["UNKNOWN_INTERNAL_ERROR"]
    return _public_text(text)


def _public_text(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "APQOEE Cumulative": "APQOEE tích lũy",
        "Cumulative OEE": "OEE tích lũy",
        "Cumulative Availability": "Availability tích lũy",
        "Cumulative Performance": "Performance tích lũy",
        "Cumulative Quality": "Quality tích lũy",
        "Machine Downtime": "Dữ liệu downtime máy",
        "Loss Assignment": "Dữ liệu phân bổ tổn thất",
        "Sources and filters": "Nguồn và bộ lọc",
        "Source": "Nguồn dữ liệu",
        "Date range": "Phạm vi thời gian",
        "Limitations": "Giới hạn phân tích",
        "hours": "giờ",
        "events": "lần",
        "machines": "máy",
        "rows returned": "dòng dữ liệu",
        "Production analytics result": "Kết quả phân tích dữ liệu",
        "Production Analytics Bundle": "Bộ dữ liệu phân tích sản xuất",
        "Clarification required": "Cần làm rõ yêu cầu",
        "Downtime duration": "Tổng thời lượng downtime",
        "Downtime event count": "Số lần dừng máy",
        "Loss duration": "Tổng thời lượng tổn thất",
        "Loss event count": "Số lần ghi nhận tổn thất",
        "Affected machines": "Số máy bị ảnh hưởng",
        "Affected máy": "Số máy bị ảnh hưởng",
        "full available range": "toàn bộ phạm vi dữ liệu hiện có",
        "clipped events": "các sự kiện được cắt theo khoảng thời gian yêu cầu",
        "clips events": "cắt sự kiện theo khoảng thời gian yêu cầu",
        "clips lần": "cắt sự kiện theo khoảng thời gian yêu cầu",
        "The requested sources were evaluated with deterministic calculations.": "Các nguồn dữ liệu đã được tính toán bằng quy trình xác định.",
        "APQOEE values are cumulative from the beginning of the dataset through the selected snapshot.": "Các chỉ số APQOEE là giá trị tích lũy từ đầu tập dữ liệu đến thời điểm snapshot được chọn.",
        "This is a cumulative OEE trend, not daily OEE.": "Đây là xu hướng OEE tích lũy, không phải OEE riêng từng ngày.",
        "Downtime uses interval overlap and clips events to the requested period.": "Downtime được tính theo phần thời gian giao với khoảng được yêu cầu.",
        "Loss uses interval overlap and clips events to the requested period.": "Tổn thất được tính theo phần thời gian giao với khoảng được yêu cầu.",
        "Please specify whether you want OEE, machine downtime, loss assignment, or a comparison across those sources.": "Bạn muốn xem OEE, downtime máy, phân bổ tổn thất hay so sánh giữa các nguồn dữ liệu này?",
        "Please clarify the metric.": "Vui lòng cho biết rõ chỉ số bạn muốn xem.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = _ISO_RE.sub(lambda match: _format_datetime_vi(match.group(0)), text)
    post_replacements = {
        "cumulative through": "Tích lũy đến",
        "Downtime uses interval overlap and cắt sự kiện theo khoảng thời gian yêu cầu đến the requested period.": "Downtime được tính theo phần thời gian giao với khoảng được yêu cầu.",
        "Loss uses interval overlap and cắt sự kiện theo khoảng thời gian yêu cầu đến the requested period.": "Tổn thất được tính theo phần thời gian giao với khoảng được yêu cầu.",
        "Downtime uses interval overlap and": "Downtime được tính theo phần thời gian giao với khoảng được yêu cầu.",
        "Loss uses interval overlap and": "Tổn thất được tính theo phần thời gian giao với khoảng được yêu cầu.",
        "the requested period": "khoảng được yêu cầu",
    }
    for old, new in post_replacements.items():
        text = text.replace(old, new)
    text = text.replace(" to ", " đến ")
    text = re.sub(r"(\d+)\.(\d{1,2})\s?%", lambda match: f"{match.group(1)},{match.group(2)}%", text)
    text = re.sub(
        r"\b(\d+)\.(\d{1,2})\s+(giờ|lần|máy)\b",
        lambda match: f"{int(match.group(1)):,}".replace(",", ".") + f",{match.group(2)} {match.group(3)}",
        text,
    )
    text = text.replace(" %", "%")
    text = text.replace("None", "").replace("NaN", "").replace("null", "")
    return text.strip()


def _source_label(value: Any) -> str:
    return SOURCE_LABELS.get(str(value), _public_text(value))


def _column_label(value: Any) -> str:
    text = str(value)
    return PUBLIC_COLUMN_LABELS.get(text, METRIC_LABELS.get(text, SOURCE_LABELS.get(text, display_label(text))))


def _unit_label(value: Any) -> str:
    return {"%": "%", "hours": "giờ", "events": "lần", "machines": "máy"}.get(str(value), str(value))


def _format_number_vi(value: Any, unit: Any = "") -> str:
    try:
        number = float(value)
        if number.is_integer():
            formatted = f"{int(number):,}".replace(",", ".")
        else:
            formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        formatted = _public_text(value)
    unit_label = _unit_label(unit)
    if unit_label == "%":
        return f"{formatted}%"
    return f"{formatted} {unit_label}".strip()


def _format_datetime_vi(value: Any) -> str:
    raw = str(value or "")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return f"{dt:%H:%M} ngày {dt:%d/%m/%Y}"
    except Exception:
        return raw


def _format_scope_vi(value: Any) -> str:
    text = str(value or "")
    text = text.replace("cumulative through", "Tích lũy đến")
    text = text.replace("cumulative snapshot trend", "Xu hướng snapshot tích lũy")
    text = text.replace(" to ", " đến ")
    return _public_text(text)


def _is_production_metric_rows(rows: list[dict[str, Any]]) -> bool:
    keys = set().union(*(row.keys() for row in rows))
    return {"metric", "value"}.issubset(keys) and ("source_id" in keys or "time_scope" in keys or "snapshot_time" in keys)


def _is_apqoee_table(table: Any) -> bool:
    rows = getattr(table, "rows", None) or []
    return bool(rows) and all(str(row.get("metric", "")).startswith("Cumulative ") for row in rows)


def _metric_row(row: dict[str, Any]) -> dict[str, Any]:
    metric = METRIC_LABELS.get(str(row.get("metric")), _public_text(row.get("metric")))
    value = _format_number_vi(row.get("value"), row.get("unit"))
    return {"Chỉ số": metric, "Giá trị": value}


def _localized_row(row: dict[str, Any], *, compact: bool) -> dict[str, Any]:
    output: dict[str, Any] = {}
    skip = {"source_id", "_source_id", "schema_fingerprint", "checksum", "data_version", "artifact_id", "query_plan_id", "query_result_id"}
    for key, value in row.items():
        if compact and str(key) in skip:
            continue
        label = _column_label(key)
        if str(key) in {"source", "source_id", "_source_id"}:
            output[label] = _source_label(value)
        elif str(key) == "metric":
            output[label] = METRIC_LABELS.get(str(value), _public_text(value))
        elif str(key) in {"time_scope", "snapshot_time", "start", "end"}:
            output[label] = _format_scope_vi(value)
        elif str(key) == "unit":
            output[label] = _unit_label(value)
        elif value is None:
            output[label] = ""
        else:
            output[label] = _public_text(value)
    return output


def _apqoee_summary(rows: list[dict[str, Any]]) -> str:
    snapshot = ""
    bullets: list[str] = []
    for row in rows:
        metric = METRIC_LABELS.get(str(row.get("metric")), str(row.get("metric") or ""))
        if not metric:
            continue
        bullets.append(f"- {metric}: {_format_number_vi(row.get('value'), row.get('unit'))}")
        if not snapshot:
            snapshot = _format_datetime_vi(row.get("snapshot_time") or "")
    scope = f"Kết quả tính đến {snapshot}:" if snapshot else "Kết quả APQOEE tích lũy:"
    return "\n\n".join(
        [
            scope,
            "\n".join(bullets),
            "Các chỉ số trên được tính tích lũy từ thời điểm bắt đầu tập dữ liệu đến thời điểm được chọn.",
            "Nguồn dữ liệu: APQOEE tích lũy",
        ]
    )
