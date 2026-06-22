from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.query.schemas import FilterSpec, MetricSpec, QueryPlan
from src.rendering.formatters import format_dataframe_for_display, format_duration, format_vn_number, humanize_column_name
from src.rendering.presentation import build_presented_response, should_show_download_button


def test_format_duration_large_value():
    value = format_duration(7_162_405)
    assert value["primary"] == "1.989,56 giờ"
    assert value["secondary"] == "82 ngày 21 giờ 33 phút 25 giây"


def test_format_duration_invalid_values():
    assert format_duration(None)["primary"] == "Không có dữ liệu"
    assert format_duration(-1)["primary"] == "Không có dữ liệu"


def test_format_vn_number():
    assert format_vn_number(1989.56, 2, False) == "1.989,56"
    assert format_vn_number(1000, 0) == "1.000"


def test_humanize_column_names_with_fallback():
    assert humanize_column_name("total_duration_seconds") == "Tổng thời gian downtime"
    assert humanize_column_name("custom_metric_name") == "Custom metric name"


def test_scalar_detection_and_no_question_echo():
    plan = QueryPlan(tables=["t"], metrics=[MetricSpec(aggregation="sum", column="thoi_luong_seconds", name="total_duration_seconds")])
    df = pd.DataFrame({"total_duration_seconds": [7_162_405]})
    presented = build_presented_response("Tổng downtime là bao nhiêu?", plan, df, {"tables": []}, [{"source": "Machine_Downtime.xlsx / Report"}])
    assert presented.response_type == "scalar"
    assert presented.primary_value == "1.989,56 giờ"
    assert "Tổng downtime là bao nhiêu" not in presented.summary
    assert "total_duration_seconds" not in presented.title


def test_table_response_formatting_hides_raw_columns():
    plan = QueryPlan(
        tables=["t"],
        dimensions=["may"],
        metrics=[MetricSpec(aggregation="sum", column="thoi_luong_seconds", name="total_duration_seconds")],
    )
    df = pd.DataFrame({"may": ["Máy 29"], "total_duration_seconds": [3600]})
    presented = build_presented_response("Máy nào downtime cao nhất?", plan, df, {"tables": []}, [])
    assert "total_duration_seconds" not in " ".join(presented.result_dataframe.columns)
    assert list(presented.result_dataframe.columns) == ["Máy", "Tổng thời gian downtime"]
    assert presented.result_dataframe.iloc[0, 1] == "1 giờ"


def test_empty_result_presentation():
    plan = QueryPlan(tables=["t"], filters=[FilterSpec(column="may", operator="equals", value="NOPE")])
    presented = build_presented_response("Không có dữ liệu", plan, pd.DataFrame(), {"tables": []}, [])
    assert presented.title == "Không có dữ liệu"
    assert "Không tìm thấy dữ liệu" in presented.summary


def test_raw_technical_column_not_in_normal_table():
    display = format_dataframe_for_display(pd.DataFrame({"total_duration_seconds": [60]}))
    assert "total_duration_seconds" not in display.columns
    assert "Tổng thời gian downtime" in display.columns


def test_download_buttons_visibility(tmp_path):
    path = tmp_path / "report.html"
    assert not should_show_download_button(path)
    path.write_text("ok", encoding="utf-8")
    assert should_show_download_button(path)
    assert not should_show_download_button(None)

