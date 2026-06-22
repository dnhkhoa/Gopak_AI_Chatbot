from __future__ import annotations

from scripts_ingest import main as ingest
from src.config import get_settings
from src.query.executor import SafeQueryExecutor
from src.query.schemas import MetricSpec, QueryPlan
from src.rendering.report_exporter import export_excel_result, export_html_report


def test_export_html_and_excel(tmp_path):
    catalog = ingest(force=False)
    table = next(table for table in catalog["tables"] if table["table_name"].startswith("machine_downtime"))["table_name"]
    plan = QueryPlan(tables=[table], dimensions=["may"], metrics=[MetricSpec(aggregation="sum", column="thoi_luong_seconds", name="total_duration_seconds")], limit=5, output="bar")
    result = SafeQueryExecutor(catalog).execute(plan)
    sources = [{"table": table, "source": "test"}]
    html = export_html_report("q", "answer", result.dataframe, plan, sources, tmp_path)
    xlsx = export_excel_result("q", "answer", result.dataframe, sources, tmp_path)
    assert html.exists()
    assert xlsx.exists()

