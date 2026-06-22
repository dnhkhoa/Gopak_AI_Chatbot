from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.io as pio

from src.rendering.chart_renderer import build_chart
from src.rendering.formatters import format_dataframe_for_display


def export_html_report(question: str, answer: str, df: pd.DataFrame, plan, sources: list[dict], reports_dir: Path) -> Path:
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"report_{timestamp}.html"
    fig = build_chart(df, plan)
    chart_html = pio.to_html(fig, full_html=False, include_plotlyjs="cdn") if fig else ""
    display_df = format_dataframe_for_display(df)
    html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>Báo cáo phân tích Excel</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#1f2937}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px}}th{{background:#f3f4f6}}</style>
</head><body>
<h1>Báo cáo phân tích Excel</h1>
<p><strong>Thời gian tạo:</strong> {datetime.now().isoformat(timespec="seconds")}</p>
<p><strong>Câu hỏi:</strong> {question}</p>
<h2>Tóm tắt</h2><p>{answer}</p>
<h2>Kết quả</h2>{display_df.to_html(index=False, escape=True) if not display_df.empty else "<p>Không có dữ liệu.</p>"}
<h2>Biểu đồ</h2>{chart_html}
<h2>Nguồn dữ liệu</h2><pre>{sources}</pre>
<h2>Bộ lọc và giả định</h2><pre>{plan.model_dump_json(indent=2)}</pre>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def export_excel_result(question: str, answer: str, df: pd.DataFrame, sources: list[dict], reports_dir: Path) -> Path:
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"result_{timestamp}.xlsx"
    display_df = format_dataframe_for_display(df)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{"Câu hỏi": question, "Tóm tắt": answer, "Thời gian tạo": datetime.now().isoformat(timespec="seconds")}]).to_excel(writer, sheet_name="Summary", index=False)
        display_df.to_excel(writer, sheet_name="Result", index=False)
        pd.DataFrame(sources).to_excel(writer, sheet_name="Sources", index=False)
    return path

