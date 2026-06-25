from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import fitz

from src.application.schemas import ChartPayload, ReportPayload, TablePayload


A4 = fitz.paper_rect("a4")
MARGIN = 48
CONTENT_WIDTH = A4.width - MARGIN * 2
ACCENT = (0.18, 0.36, 0.62)
LIGHT = (0.93, 0.96, 0.99)
BORDER = (0.78, 0.82, 0.88)
TEXT = (0.12, 0.15, 0.20)
MUTED = (0.42, 0.47, 0.55)
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
    )
    ctx.new_page()
    ctx.cover()
    ctx.executive_summary()
    ctx.kpis()
    for section in report.sections:
        ctx.section(section)
    ctx.limitations()
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
    text = "\n".join(page.get_text("text") for page in doc)
    verification = {
        "page_count": len(doc),
        "blank_pages": blank_pages,
        "has_vietnamese": any(token in text for token in ["Báo cáo", "Tổng", "Nguồn", "Giới hạn"]),
        "metadata_leakage": [token for token in FORBIDDEN_PUBLIC_TOKENS if token in text],
        "contains_pdf_title": report_title_in_text(text),
    }
    doc.close()
    return images, verification


def report_title_in_text(text: str) -> bool:
    normalized = " ".join(str(text or "").replace("\xa0", " ").split())
    return "Báo cáo phân tích downtime" in normalized or "Báo cáo tổng quan" in normalized


class _PdfContext:
    def __init__(self, *, doc: fitz.Document, report: ReportPayload, font_regular: str, font_bold: str) -> None:
        self.doc = doc
        self.report = report
        self.font_regular = font_regular
        self.font_bold = font_bold
        self.page: fitz.Page | None = None
        self.y = MARGIN

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=A4.width, height=A4.height)
        self.y = MARGIN

    def ensure(self, height: float) -> None:
        if self.y + height > A4.height - MARGIN - 22:
            self.new_page()

    def text(self, rect: fitz.Rect, value: Any, size: float = 10, color=TEXT, bold: bool = False, align: int = fitz.TEXT_ALIGN_LEFT) -> None:
        assert self.page is not None
        self.page.insert_textbox(
            rect,
            _clean(value),
            fontsize=size,
            fontname="gopak-bold" if bold else "gopak",
            fontfile=self.font_bold if bold else self.font_regular,
            color=color,
            align=align,
        )

    def cover(self) -> None:
        assert self.page is not None
        self.page.draw_rect(fitz.Rect(0, 0, A4.width, 130), color=None, fill=LIGHT)
        self.text(fitz.Rect(MARGIN, 44, A4.width - MARGIN, 68), "iSoft", 18, ACCENT, True)
        self.text(fitz.Rect(MARGIN, 78, A4.width - MARGIN, 116), self.report.title, 22, TEXT, True)
        if self.report.subtitle:
            self.text(fitz.Rect(MARGIN, 118, A4.width - MARGIN, 150), self.report.subtitle, 11, MUTED)
        self.y = 170
        meta = [
            ("File nguồn", self.report.source_file_name or self.report.source.name),
            ("Phạm vi dữ liệu", _date_range_text(self.report.date_range)),
            ("Thời gian tạo", self.report.generated_at),
            ("Mục tiêu", "Tổng hợp downtime, máy/nguyên nhân nổi bật, xu hướng và giới hạn diễn giải."),
        ]
        for label, value in meta:
            self.text(fitz.Rect(MARGIN, self.y, MARGIN + 110, self.y + 22), label, 10, MUTED, True)
            self.text(fitz.Rect(MARGIN + 118, self.y, A4.width - MARGIN, self.y + 22), value, 10, TEXT)
            self.y += 26

    def executive_summary(self) -> None:
        self.heading("Tóm tắt điều hành")
        for item in self.report.executive_summary[:5]:
            self.bullet(item)

    def kpis(self) -> None:
        self.heading("KPI tổng quan")
        card_w = (CONTENT_WIDTH - 18) / 4
        card_h = 82
        self.ensure(card_h + 12)
        y = self.y
        for idx, kpi in enumerate(self.report.kpis[:4]):
            x = MARGIN + idx * (card_w + 6)
            rect = fitz.Rect(x, y, x + card_w, y + card_h)
            assert self.page is not None
            self.page.draw_rect(rect, color=BORDER, fill=(0.98, 0.99, 1.0))
            self.text(fitz.Rect(x + 8, y + 9, x + card_w - 8, y + 26), kpi.label, 8.5, MUTED, True)
            value = f"{kpi.value} {kpi.unit}".strip() if kpi.unit else kpi.value
            self.text(fitz.Rect(x + 8, y + 30, x + card_w - 8, y + 54), value, 13, ACCENT, True)
            if kpi.hint:
                self.text(fitz.Rect(x + 8, y + 58, x + card_w - 8, y + 78), kpi.hint, 7.2, MUTED)
        self.y += card_h + 16

    def section(self, section: Any) -> None:
        self.heading(section.title)
        if section.summary:
            self.paragraph(section.summary)
        if section.kpis:
            for kpi in section.kpis:
                value = f"{kpi.value} {kpi.unit}".strip() if kpi.unit else kpi.value
                self.bullet(f"{kpi.label}: {value}")
        for item in section.commentary[:4]:
            self.bullet(item)
        if section.chart:
            self.chart(section.chart)
        if section.table:
            self.table(section.table, max_rows=12 if section.section_type == "xu_huong" else 8)

    def limitations(self) -> None:
        self.heading("Nguồn, bộ lọc và giới hạn")
        self.paragraph(f"Nguồn dữ liệu: {self.report.source_file_name or self.report.source.name}.")
        self.paragraph(f"Phạm vi: {_date_range_text(self.report.date_range)}.")
        self.paragraph("Bộ lọc: Không áp dụng.")
        for item in self.report.limitations:
            self.bullet(item)

    def heading(self, value: str) -> None:
        self.ensure(44)
        self.text(fitz.Rect(MARGIN, self.y, A4.width - MARGIN, self.y + 24), value, 14, ACCENT, True)
        self.y += 28

    def paragraph(self, value: str) -> None:
        height = max(28, 12 * (len(str(value)) // 88 + 1))
        self.ensure(height)
        self.text(fitz.Rect(MARGIN, self.y, A4.width - MARGIN, self.y + height), value, 9.5, TEXT)
        self.y += height + 4

    def bullet(self, value: str) -> None:
        height = max(24, 12 * (len(str(value)) // 92 + 1))
        self.ensure(height)
        self.text(fitz.Rect(MARGIN, self.y, MARGIN + 12, self.y + height), "-", 10, ACCENT, True)
        self.text(fitz.Rect(MARGIN + 16, self.y, A4.width - MARGIN, self.y + height), value, 9.2, TEXT)
        self.y += height + 2

    def table(self, table: TablePayload, max_rows: int = 8) -> None:
        rows = table.rows[:max_rows]
        if not rows:
            return
        cols = table.columns[:5]
        row_h = 22
        height = row_h * (len(rows) + 1) + 10
        self.ensure(height)
        col_w = CONTENT_WIDTH / len(cols)
        assert self.page is not None
        y = self.y
        for i, col in enumerate(cols):
            x = MARGIN + i * col_w
            self.page.draw_rect(fitz.Rect(x, y, x + col_w, y + row_h), color=BORDER, fill=LIGHT)
            self.text(fitz.Rect(x + 4, y + 5, x + col_w - 4, y + row_h), str(col), 7.8, TEXT, True)
        y += row_h
        for ridx, row in enumerate(rows):
            fill = (1, 1, 1) if ridx % 2 == 0 else (0.97, 0.98, 0.99)
            for i, col in enumerate(cols):
                x = MARGIN + i * col_w
                self.page.draw_rect(fitz.Rect(x, y, x + col_w, y + row_h), color=BORDER, fill=fill)
                align = fitz.TEXT_ALIGN_RIGHT if _looks_number(row.get(col)) else fitz.TEXT_ALIGN_LEFT
                self.text(fitz.Rect(x + 4, y + 5, x + col_w - 4, y + row_h), row.get(col, ""), 7.6, TEXT, align=align)
            y += row_h
        self.y = y + 12

    def chart(self, chart: ChartPayload) -> None:
        self.ensure(210)
        assert self.page is not None
        rect = fitz.Rect(MARGIN, self.y, A4.width - MARGIN, self.y + 190)
        self.page.draw_rect(rect, color=BORDER, fill=(1, 1, 1))
        self.text(fitz.Rect(rect.x0 + 12, rect.y0 + 8, rect.x1 - 12, rect.y0 + 28), chart.title or "Biểu đồ", 10, TEXT, True)
        plot = fitz.Rect(rect.x0 + 48, rect.y0 + 42, rect.x1 - 24, rect.y1 - 34)
        self.page.draw_line(fitz.Point(plot.x0, plot.y1), fitz.Point(plot.x1, plot.y1), color=BORDER)
        self.page.draw_line(fitz.Point(plot.x0, plot.y0), fitz.Point(plot.x0, plot.y1), color=BORDER)
        data = chart.data[:12]
        values = [_number_from_row(row, chart.y_keys[0] if chart.y_keys else "") for row in data]
        max_v = max(values) if values else 1
        if chart.type == "line":
            points = []
            for idx, value in enumerate(values):
                x = plot.x0 + idx * (plot.width / max(1, len(values) - 1))
                y = plot.y1 - (value / max_v) * plot.height if max_v else plot.y1
                points.append(fitz.Point(x, y))
            for a, b in zip(points, points[1:]):
                self.page.draw_line(a, b, color=ACCENT, width=1.4)
            for point in points:
                self.page.draw_circle(point, 2.5, color=ACCENT, fill=ACCENT)
            unit = chart.y_axis_unit or chart.tooltip_unit or "giờ"
            y_key = chart.y_keys[0] if chart.y_keys else "Giá trị"
            self.text(fitz.Rect(plot.x0, plot.y1 + 6, plot.x1, plot.y1 + 22), f"Trục X: {chart.x_key} | Trục Y: {y_key} ({unit})", 7.5, MUTED)
        else:
            bar_h = min(14, plot.height / max(1, len(data)) - 4)
            for idx, (row, value) in enumerate(zip(data, values)):
                y = plot.y0 + idx * (bar_h + 5)
                width = (value / max_v) * (plot.width - 80) if max_v else 0
                fill = ACCENT if value == max_v else (0.45, 0.58, 0.78)
                self.page.draw_rect(fitz.Rect(plot.x0 + 80, y, plot.x0 + 80 + width, y + bar_h), color=None, fill=fill)
                self.text(fitz.Rect(plot.x0, y - 1, plot.x0 + 76, y + bar_h + 2), str(row.get(chart.x_key, ""))[:18], 7, TEXT)
            self.text(fitz.Rect(plot.x0, plot.y1 + 6, plot.x1, plot.y1 + 22), f"Đơn vị: {chart.y_axis_unit or chart.tooltip_unit or 'giờ'}", 7.5, MUTED)
        self.y += 202

    def footer_all_pages(self) -> None:
        total = len(self.doc)
        for idx, page in enumerate(self.doc, start=1):
            page.insert_textbox(
                fitz.Rect(MARGIN, 22, A4.width - MARGIN, 38),
                self.report.title,
                fontsize=8,
                fontname="gopak",
                fontfile=self.font_regular,
                color=MUTED,
            )
            page.insert_textbox(
                fitz.Rect(MARGIN, A4.height - 34, A4.width - MARGIN, A4.height - 18),
                f"{self.report.source_file_name or self.report.source.name} | Trang {idx}/{total}",
                fontsize=8,
                fontname="gopak",
                fontfile=self.font_regular,
                color=MUTED,
                align=fitz.TEXT_ALIGN_CENTER,
            )


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
        return "không xác định"
    start = date_range.get("from") or date_range.get("start")
    end = date_range.get("to") or date_range.get("end")
    return f"{_date_text(start)} - {_date_text(end)}" if start and end else "không xác định"


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
