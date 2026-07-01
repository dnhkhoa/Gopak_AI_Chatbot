from __future__ import annotations

import fitz

from src.application.schemas import ChartPayload, KpiCard, PublicReportSection, ReportPayload, SourceInfo, TablePayload
from src.rendering.pdf_report import export_public_report_pdf


def test_customer_pdf_report_layout_uses_payload_and_hides_internal_columns(tmp_path):
    report = ReportPayload(
        report_id="layout-test",
        root_report_id="layout-test",
        revision_number=2,
        title="Báo cáo tình hình sản xuất",
        subtitle="Tổng hợp từ payload kiểm thử",
        source_file_name="Production Analytics Bundle",
        date_range=None,
        generated_at="09:00, ngày 27/06/2026",
        executive_summary=["Báo cáo sử dụng dữ liệu đã có trong payload và không tự tạo số liệu mới."],
        kpis=[KpiCard(label="Tổng downtime", value="42,5", unit="giờ", hint="Theo payload.")],
        source=SourceInfo(name="Production Analytics Bundle", rows=100),
        filters=[],
        limitations=["Giới hạn phân tích được truyền từ payload."],
        completeness={},
        sections=[
            PublicReportSection(
                section_type="table",
                title="Bảng top máy",
                summary="Bảng này kiểm tra cột công khai.",
                table=TablePayload(
                    columns=["machine", "downtime_hours", "source_id", "artifact_id"],
                    rows=[{"machine": "Máy 11", "downtime_hours": 42.5, "source_id": "hidden", "artifact_id": "a1"}],
                ),
            ),
            PublicReportSection(
                section_type="chart",
                title="Biểu đồ downtime",
                summary="Biểu đồ dùng đúng payload.",
                chart=ChartPayload(
                    type="line",
                    title="Downtime theo ngày",
                    x_key="date_label",
                    y_keys=["downtime_hours"],
                    y_axis_unit="giờ",
                    data=[{"date_label": "14/11", "downtime_hours": 42.5}],
                ),
            ),
        ],
    )

    result = export_public_report_pdf(report, tmp_path)
    doc = fitz.open(result.pdf_path)
    text = "\n".join(page.get_text("text") for page in doc).replace("\xa0", " ")
    doc.close()

    assert result.pdf_path.exists()
    assert result.verification["blank_pages"] == 0
    assert result.verification["metadata_leakage"] == []
    assert "iSoft" in text
    assert "Báo cáo tình hình sản xuất" in text
    assert "Không xác định" in text
    assert "Máy 11" in text
    assert "source_id" not in text
    assert "artifact_id" not in text
    assert "Gopak" not in text
    assert "Demo" not in text
