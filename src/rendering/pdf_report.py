from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import fitz

from src.application.schemas import ChartPayload, ReportPayload, TablePayload


A4 = fitz.paper_rect("a4")
MARGIN_X = 48
MARGIN_TOP = 48
MARGIN_BOTTOM = 56
CONTENT_WIDTH = A4.width - MARGIN_X * 2
PRIMARY = (0.09, 0.23, 0.42)
SECONDARY = (0.18, 0.40, 0.66)
LIGHT = (0.93, 0.96, 0.98)
VERY_LIGHT = (0.97, 0.98, 0.99)
BORDER = (0.85, 0.89, 0.93)
TEXT = (0.12, 0.16, 0.22)
MUTED = (0.39, 0.45, 0.55)
WHITE = (1, 1, 1)
UNKNOWN = "Không xác định"
INTERNAL_COLUMNS = {
    "source_id",
    "artifact_id",
    "query_result_id",
    "query_plan_id",
    "schema_version",
    "canonical_metric_key",
    "canonical metric key",
    "result_id",
}
COLUMN_LABELS = {
    "metric": "Chỉ số",
    "value": "Giá trị",
    "unit": "Đơn vị",
    "time_scope": "Phạm vi",
    "snapshot_time": "Thời điểm",
    "source": "Nguồn",
    "machine": "Máy",
    "downtime_hours": "Downtime",
    "event_count": "Số lần",
    "loss_group": "Nhóm tổn thất",
    "date_label": "Ngày",
}
FORBIDDEN_PUBLIC_TOKENS = [
    "SUCCESS",
    "NaN",
    "dataset_overview",
    "kpi_total_downtime",
    "management_commentary",
    "query_plan_id",
    "result_id",
    "fallback",
    "REAL_LLM",
    "execution_mode",
    "Report includes overview",
    "Sources and filters",
    "DEMO READY",
    "Demo",
    "Gopak",
]


@dataclass
class PdfRenderResult:
    pdf_path: Path
    page_count: int
    preview_images: list[Path]
    verification: dict[str, Any]


def export_public_report_pdf(report: ReportPayload, reports_dir: Path) -> PdfRenderResult:
    reports_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = reports_dir / f"report_{report.report_id}.pdf"
    doc = fitz.open()
    ctx = _PdfContext(
        doc=doc,
        report=report,
        font_regular=_font_path(False),
        font_bold=_font_path(True),
        logo_path=_logo_path(),
    )
    ctx.new_page()
    ctx.cover()
    if _has_text_items(report.executive_summary):
        ctx.executive_summary()
    if report.kpis:
        ctx.kpis()
    for section in [item for item in report.sections if _section_has_content(item) and not _is_source_limit_section(item)]:
        ctx.section(section)
    ctx.sources_and_limits()
    ctx.footer_all_pages()
    doc.save(pdf_path, garbage=4, deflate=True)
    doc.close()
    preview_images, verification = render_pdf_pages(pdf_path, reports_dir.parent / "artifacts" / "pdf_render_verification")
    return PdfRenderResult(pdf_path=pdf_path, page_count=len(preview_images), preview_images=preview_images, verification=verification)


def render_pdf_pages(pdf_path: Path, output_dir: Path) -> tuple[list[Path], dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    images: list[Path] = []
    blank_pages = 0
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
        out = output_dir / f"{pdf_path.stem}_page_{index}.png"
        pix.save(out)
        images.append(out)
        if len(page.get_text("text").strip()) < 40:
            blank_pages += 1
    text = "\n".join(page.get_text("text") for page in doc).replace("\xa0", " ")
    verification = {
        "page_count": len(doc),
        "blank_pages": blank_pages,
        "has_vietnamese": any(token in text for token in ["Báo cáo", "Tổng", "Nguồn", "Giới hạn"]),
        "metadata_leakage": [token for token in FORBIDDEN_PUBLIC_TOKENS if token in text],
        "contains_pdf_title": "Báo cáo" in text,
    }
    doc.close()
    return images, verification


class _PdfContext:
    def __init__(self, *, doc: fitz.Document, report: ReportPayload, font_regular: str, font_bold: str, logo_path: Path | None) -> None:
        self.doc = doc
        self.report = report
        self.font_regular = font_regular
        self.font_bold = font_bold
        self.logo_path = logo_path
        self.page: fitz.Page | None = None
        self.y = MARGIN_TOP

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=A4.width, height=A4.height)
        self.y = MARGIN_TOP

    def ensure(self, height: float) -> None:
        if self.y + height > A4.height - MARGIN_BOTTOM:
            self.new_page()

    def text(self, rect: fitz.Rect, value: Any, size: float = 10, color=TEXT, bold: bool = False, align: int = fitz.TEXT_ALIGN_LEFT) -> None:
        assert self.page is not None
        self.page.insert_textbox(
            rect,
            _clean(value),
            fontsize=size,
            fontname="report-bold" if bold else "report",
            fontfile=self.font_bold if bold else self.font_regular,
            color=color,
            align=align,
        )

    def cover(self) -> None:
        assert self.page is not None
        if self.logo_path and self.logo_path.exists():
            self.page.insert_image(fitz.Rect(MARGIN_X, MARGIN_TOP, MARGIN_X + 118, MARGIN_TOP + 38), filename=str(self.logo_path), keep_proportion=True)
        else:
            self.text(fitz.Rect(MARGIN_X, MARGIN_TOP + 8, MARGIN_X + 118, MARGIN_TOP + 34), "iSoft", 16, PRIMARY, True)
        self.text(fitz.Rect(MARGIN_X + 150, MARGIN_TOP, A4.width - MARGIN_X, MARGIN_TOP + 44), _display(self.report.title), 20, PRIMARY, True, fitz.TEXT_ALIGN_RIGHT)
        y_rule = MARGIN_TOP + 54
        self.page.draw_line(fitz.Point(MARGIN_X, y_rule), fitz.Point(A4.width - MARGIN_X, y_rule), color=PRIMARY, width=1.2)
        self.y = y_rule + 24
        self.text(fitz.Rect(MARGIN_X, self.y, A4.width - MARGIN_X, self.y + 28), _display(self.report.title), 16, TEXT, True)
        self.y += 32
        if _valid_text(self.report.subtitle):
            self.paragraph(self.report.subtitle, color=MUTED, size=9.2)
        self.metadata_block(
            [
                ("File nguồn", self.report.source_file_name or self.report.source.name or UNKNOWN),
                ("Phạm vi dữ liệu", _date_range_text(self.report.date_range)),
                ("Thời gian tạo", self.report.generated_at or UNKNOWN),
                ("Mục tiêu", _report_purpose(self.report)),
            ]
        )
        self.y += 10

    def metadata_block(self, rows: list[tuple[str, Any]]) -> None:
        self.ensure(30 * len(rows) + 4)
        for label, value in rows:
            assert self.page is not None
            self.page.draw_rect(fitz.Rect(MARGIN_X, self.y, MARGIN_X + 122, self.y + 30), color=BORDER, fill=LIGHT)
            self.page.draw_rect(fitz.Rect(MARGIN_X + 122, self.y, A4.width - MARGIN_X, self.y + 30), color=BORDER, fill=WHITE)
            self.text(fitz.Rect(MARGIN_X + 8, self.y + 8, MARGIN_X + 114, self.y + 25), label, 8, PRIMARY, True)
            self.text(fitz.Rect(MARGIN_X + 132, self.y + 8, A4.width - MARGIN_X - 8, self.y + 25), _display(value), 8.4, TEXT)
            self.y += 30

    def executive_summary(self) -> None:
        self.heading("Tóm tắt điều hành")
        for item in [item for item in self.report.executive_summary if _valid_text(item)][:5]:
            self.bullet(item)

    def kpis(self) -> None:
        self.heading("KPI tổng quan")
        card_w = (CONTENT_WIDTH - 18) / 4
        card_h = 74
        for row_start in range(0, len(self.report.kpis[:8]), 4):
            row = self.report.kpis[row_start : row_start + 4]
            self.ensure(card_h + 12)
            y = self.y
            for idx, kpi in enumerate(row):
                x = MARGIN_X + idx * (card_w + 6)
                assert self.page is not None
                self.page.draw_rect(fitz.Rect(x, y, x + card_w, y + card_h), color=BORDER, fill=VERY_LIGHT)
                self.text(fitz.Rect(x + 8, y + 8, x + card_w - 8, y + 26), _display(kpi.label), 7.5, MUTED, True)
                value = f"{kpi.value} {kpi.unit}".strip() if kpi.unit else _display(kpi.value)
                self.text(fitz.Rect(x + 8, y + 30, x + card_w - 8, y + 52), value, 11, PRIMARY, True)
                if _valid_text(kpi.hint):
                    self.text(fitz.Rect(x + 8, y + 55, x + card_w - 8, y + 70), kpi.hint, 6.6, MUTED)
            self.y += card_h + 10

    def section(self, section: Any) -> None:
        self.heading(_display(section.title))
        if _valid_text(section.summary):
            self.paragraph(section.summary)
        if section.kpis:
            for row_start in range(0, len(section.kpis), 2):
                self.ensure(64)
                for idx, kpi in enumerate(section.kpis[row_start : row_start + 2]):
                    card_w = (CONTENT_WIDTH - 8) / 2
                    x = MARGIN_X + idx * (card_w + 8)
                    y = self.y
                    assert self.page is not None
                    self.page.draw_rect(fitz.Rect(x, y, x + card_w, y + 56), color=BORDER, fill=VERY_LIGHT)
                    self.text(fitz.Rect(x + 8, y + 7, x + card_w - 8, y + 23), _display(kpi.label), 7.3, MUTED, True)
                    self.text(fitz.Rect(x + 8, y + 27, x + card_w - 8, y + 48), f"{kpi.value} {kpi.unit or ''}".strip(), 9.3, PRIMARY, True)
                self.y += 64
        for item in [item for item in section.commentary if _valid_text(item)][:6]:
            self.bullet(item)
        if section.chart and _chart_has_data(section.chart):
            self.chart(section.chart)
        if section.table and section.table.rows:
            self.table(section.table, max_rows=12 if section.section_type == "xu_huong" else 8)

    def sources_and_limits(self) -> None:
        title = "Nguồn dữ liệu và giới hạn phân tích" if _has_text_items(self.report.limitations) else "Nguồn dữ liệu và bộ lọc"
        self.heading(title)
        self.metadata_block(
            [
                ("Nguồn dữ liệu", self.report.source_file_name or self.report.source.name or UNKNOWN),
                ("Phạm vi", _date_range_text(self.report.date_range)),
                ("Bộ lọc", _filters_text(self.report.filters)),
            ]
        )
        self.y += 8
        for item in [item for item in self.report.limitations if _valid_text(item)]:
            self.bullet(item)

    def heading(self, value: str) -> None:
        self.ensure(70)
        self.text(fitz.Rect(MARGIN_X, self.y, A4.width - MARGIN_X, self.y + 22), value, 12.5, PRIMARY, True)
        self.y += 25

    def paragraph(self, value: str, color=TEXT, size: float = 9) -> None:
        height = max(24, 11 * (len(str(value)) // 92 + 1))
        self.ensure(height)
        self.text(fitz.Rect(MARGIN_X, self.y, A4.width - MARGIN_X, self.y + height), value, size, color)
        self.y += height + 5

    def bullet(self, value: str) -> None:
        height = max(22, 11 * (len(str(value)) // 88 + 1))
        self.ensure(height)
        self.text(fitz.Rect(MARGIN_X, self.y, MARGIN_X + 12, self.y + height), "-", 9.5, PRIMARY, True)
        self.text(fitz.Rect(MARGIN_X + 16, self.y, A4.width - MARGIN_X, self.y + height), value, 8.7, TEXT)
        self.y += height + 2

    def table(self, table: TablePayload, max_rows: int = 8) -> None:
        rows = table.rows[:max_rows]
        cols = _public_columns(table)[:6]
        if not rows or not cols:
            return
        header_h = 24
        col_w = CONTENT_WIDTH / len(cols)
        self.ensure(header_h + 30)
        assert self.page is not None
        y = self.y
        for i, col in enumerate(cols):
            x = MARGIN_X + i * col_w
            self.page.draw_rect(fitz.Rect(x, y, x + col_w, y + header_h), color=BORDER, fill=LIGHT)
            self.text(fitz.Rect(x + 5, y + 6, x + col_w - 5, y + header_h), _column_label(col), 7.2, PRIMARY, True)
        self.y += header_h
        for ridx, row in enumerate(rows):
            row_h = max(24, 10 * max(1, max(len(str(row.get(col, ""))) // 20 + 1 for col in cols)))
            self.ensure(row_h)
            y = self.y
            fill = WHITE if ridx % 2 == 0 else VERY_LIGHT
            for i, col in enumerate(cols):
                x = MARGIN_X + i * col_w
                self.page.draw_rect(fitz.Rect(x, y, x + col_w, y + row_h), color=BORDER, fill=fill)
                align = fitz.TEXT_ALIGN_RIGHT if _looks_number(row.get(col)) else fitz.TEXT_ALIGN_LEFT
                self.text(fitz.Rect(x + 5, y + 5, x + col_w - 5, y + row_h - 2), _display(row.get(col)), 7.2, TEXT, align=align)
            self.y += row_h
        self.y += 12

    def chart(self, chart: ChartPayload) -> None:
        self.ensure(218)
        assert self.page is not None
        rect = fitz.Rect(MARGIN_X, self.y, A4.width - MARGIN_X, self.y + 198)
        self.page.draw_rect(rect, color=BORDER, fill=WHITE)
        self.text(fitz.Rect(rect.x0 + 12, rect.y0 + 9, rect.x1 - 12, rect.y0 + 28), chart.title or "Biểu đồ", 9, TEXT, True)
        plot = fitz.Rect(rect.x0 + 48, rect.y0 + 44, rect.x1 - 26, rect.y1 - 36)
        self.page.draw_line(fitz.Point(plot.x0, plot.y1), fitz.Point(plot.x1, plot.y1), color=BORDER)
        self.page.draw_line(fitz.Point(plot.x0, plot.y0), fitz.Point(plot.x0, plot.y1), color=BORDER)
        data = chart.data[:12]
        y_key = chart.y_keys[0] if chart.y_keys else ""
        values = [_number_from_row(row, y_key) for row in data]
        max_v = max(values) if values else 1
        if chart.type == "line":
            points = []
            for idx, value in enumerate(values):
                x = plot.x0 + idx * (plot.width / max(1, len(values) - 1))
                y = plot.y1 - (value / max_v) * plot.height if max_v else plot.y1
                points.append(fitz.Point(x, y))
            for a, b in zip(points, points[1:]):
                self.page.draw_line(a, b, color=SECONDARY, width=1.4)
            for point in points:
                self.page.draw_circle(point, 2.3, color=SECONDARY, fill=SECONDARY)
        else:
            bar_h = min(14, plot.height / max(1, len(data)) - 4)
            for idx, (row, value) in enumerate(zip(data, values)):
                if chart.type == "horizontal_bar":
                    y = plot.y0 + idx * (bar_h + 5)
                    width = (value / max_v) * (plot.width - 88) if max_v else 0
                    self.page.draw_rect(fitz.Rect(plot.x0 + 88, y, plot.x0 + 88 + width, y + bar_h), color=None, fill=SECONDARY)
                    self.text(fitz.Rect(plot.x0, y - 1, plot.x0 + 82, y + bar_h + 2), str(row.get(chart.x_key, ""))[:20], 6.8, TEXT)
                else:
                    bar_w = max(8, (plot.width / max(1, len(data))) * 0.55)
                    x = plot.x0 + idx * (plot.width / max(1, len(data)))
                    height = (value / max_v) * plot.height if max_v else 0
                    self.page.draw_rect(fitz.Rect(x, plot.y1 - height, x + bar_w, plot.y1), color=None, fill=SECONDARY)
        unit = chart.y_axis_unit or chart.tooltip_unit or ""
        self.text(fitz.Rect(plot.x0, plot.y1 + 7, plot.x1, plot.y1 + 23), f"Trục X: {_display(chart.x_key)} | Trục Y: {_column_label(y_key)}{f' ({unit})' if unit else ''}", 7.2, MUTED)
        self.y += 210

    def footer_all_pages(self) -> None:
        total = len(self.doc)
        short_title = _shorten(_display(self.report.title), 72)
        for idx, page in enumerate(self.doc, start=1):
            page.draw_line(fitz.Point(MARGIN_X, A4.height - 42), fitz.Point(A4.width - MARGIN_X, A4.height - 42), color=BORDER, width=0.7)
            page.insert_textbox(
                fitz.Rect(MARGIN_X, A4.height - 34, MARGIN_X + 80, A4.height - 18),
                "iSoft",
                fontsize=7.5,
                fontname="report",
                fontfile=self.font_regular,
                color=MUTED,
            )
            page.insert_textbox(
                fitz.Rect(MARGIN_X + 84, A4.height - 34, A4.width - MARGIN_X - 72, A4.height - 18),
                short_title,
                fontsize=7.5,
                fontname="report",
                fontfile=self.font_regular,
                color=MUTED,
                align=fitz.TEXT_ALIGN_CENTER,
            )
            page.insert_textbox(
                fitz.Rect(A4.width - MARGIN_X - 70, A4.height - 34, A4.width - MARGIN_X, A4.height - 18),
                f"Trang {idx} / {total}",
                fontsize=7.5,
                fontname="report",
                fontfile=self.font_regular,
                color=MUTED,
                align=fitz.TEXT_ALIGN_RIGHT,
            )


def _logo_path() -> Path | None:
    path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets" / "isoft-logo.png"
    return path if path.exists() else None


def _has_text_items(values: list[Any]) -> bool:
    return any(_valid_text(value) for value in values)


def _valid_text(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) < 2:
        return False
    return text.lower() not in {"none", "null", "nan", "-", "..."}


def _section_has_content(section: Any) -> bool:
    return bool(
        str(getattr(section, "title", "") or "").strip()
        and (
            _valid_text(getattr(section, "summary", None))
            or bool(getattr(section, "kpis", []))
            or _has_text_items(list(getattr(section, "commentary", []) or []))
            or (getattr(section, "table", None) is not None and bool(getattr(section.table, "rows", [])))
            or _chart_has_data(getattr(section, "chart", None))
        )
    )


def _is_source_limit_section(section: Any) -> bool:
    key = f"{getattr(section, 'section_type', '')} {getattr(section, 'title', '')}".lower()
    return ("nguồn" in key and "giới hạn" in key) or ("source" in key and "limit" in key)


def _chart_has_data(chart: ChartPayload | None) -> bool:
    return bool(chart and chart.data and chart.y_keys)


def _public_columns(table: TablePayload) -> list[str]:
    return [column for column in table.columns if column.lower() not in INTERNAL_COLUMNS]


def _column_label(column: str) -> str:
    return COLUMN_LABELS.get(column.lower(), column.replace("_", " "))


def _report_purpose(report: ReportPayload) -> str:
    completeness = report.completeness or {}
    value = completeness.get("purpose") or completeness.get("objective")
    layout = completeness.get("layout_config")
    if not value and isinstance(layout, dict):
        value = layout.get("purpose")
    return _display(value)


def _filters_text(filters: list[dict[str, Any]]) -> str:
    parts = []
    for item in filters:
        label = _display(item.get("label"))
        operator = _display(item.get("operator"))
        value = _display(item.get("value"))
        text = " ".join(part for part in [label, operator, value] if part != UNKNOWN)
        if text:
            parts.append(text)
    return "; ".join(parts) if parts else UNKNOWN


def _display(value: Any) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, float):
        if not value == value:
            return UNKNOWN
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if not value.is_integer() else f"{int(value):,}".replace(",", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    text = str(value).strip()
    return text if text else UNKNOWN


def _shorten(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _font_path(bold: bool) -> str:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    import matplotlib.font_manager as fm

    return fm.findfont("DejaVu Sans")


def _date_range_text(date_range: dict[str, Any] | None) -> str:
    if not date_range:
        return UNKNOWN
    start = date_range.get("from") or date_range.get("start")
    end = date_range.get("to") or date_range.get("end")
    return f"{_date_text(start)} - {_date_text(end)}" if start and end else UNKNOWN


def _date_text(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except Exception:
        return str(value or "")


def generated_at_vn() -> str:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    return now.strftime("%H:%M, ngày %d/%m/%Y")


def _clean(value: Any) -> str:
    text = str(value or "").replace("NaN", "").replace("nan", "")
    return " ".join(text.split())


def _looks_number(value: Any) -> bool:
    text = str(value or "")
    return any(ch.isdigit() for ch in text) and not any(ch.isalpha() for ch in text.replace("giờ", ""))


def _number_from_row(row: dict[str, Any], key: str) -> float:
    raw = row.get(key)
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "").replace(".", "").replace(",", ".")
    match = __import__("re").search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0.0
