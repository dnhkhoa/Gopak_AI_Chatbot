# Complex Query Failures

## CQ-010 - COMPLEX_DECOMPOSITION_ERROR

- Question: Trong tháng gần nhất có trong dữ liệu, hãy tìm 5 máy có tổng downtime cao nhất, hiển thị thêm số lần dừng và thời lượng trung bình, sắp xếp giảm dần và vẽ biểu đồ cột.
- Notes: Wrong output.
- Plan: `{"intent": "chart", "tables": ["machine_downtime_20260203_100753_report_3c3f6d"], "joins": [], "filters": [{"column": "thoi_gian_bat_dau", "operator": "date_between", "value": ["2026-02-01", "2026-03-01"]}], "dimensions": ["may"], "metrics": [{"name": "total_duration_seconds", "alias": "total_duration_seconds", "aggregation": "sum", "column": "thoi_luong_seconds", "percentage_of_total": false}, {"name": "row_count", "alias": "row_count", "aggregation": "count", "column": null, "percentage_of_total": false}, {"name": "avg_duration_seconds", "alias": "avg_duration_seconds", "aggregation": "avg", "column": "thoi_luong_seconds", "percentage_of_total": false}], "having": [], "ranking": null, "derived_metrics": [], "time_comparison": null, "time_granularity": null, "sort": [{"column": "total_duration_seconds", "field": "total_duration_seconds", "direction": "desc"}], "limit": 1, "output": "pie", "query_complexity": "complex", "clarification_question": null}`

## CQ-011 - COMPLEX_DECOMPOSITION_ERROR

- Question: Trong tháng gần nhất, tìm top 5 máy theo tổng downtime, chỉ giữ máy cao hơn mức trung bình, và vẽ biểu đồ cột.
- Notes: Wrong output.
- Plan: `{"intent": "chart", "tables": ["machine_downtime_20260203_100753_report_3c3f6d"], "joins": [], "filters": [{"column": "thoi_gian_bat_dau", "operator": "date_between", "value": ["2026-02-01", "2026-03-01"]}], "dimensions": ["may"], "metrics": [{"name": "total_duration_seconds", "alias": "total_duration_seconds", "aggregation": "sum", "column": "thoi_luong_seconds", "percentage_of_total": false}], "having": [{"metric_alias": "total_duration_seconds", "operator": "greater_than", "comparison": "group_average", "value": null}], "ranking": null, "derived_metrics": [], "time_comparison": null, "time_granularity": null, "sort": [{"column": "total_duration_seconds", "field": "total_duration_seconds", "direction": "desc"}], "limit": 5, "output": "pie", "query_complexity": "complex", "clarification_question": null}`

## CQ-016 - RESULT_COMPARISON_ERROR

- Question: So sánh tháng đầu tiên và tháng gần nhất về tổng downtime, số lần dừng và thời lượng trung bình.
- Notes: Missing column total_duration_seconds.
- Plan: `{"intent": "query", "tables": ["machine_downtime_20260203_100753_report_3c3f6d"], "joins": [], "filters": [], "dimensions": ["thoi_gian_bat_dau", "thoi_gian_bat_dau"], "metrics": [{"name": "total_downtime_first_month", "alias": "total_downtime_first_month", "aggregation": "sum", "column": "thoi_luong_seconds", "percentage_of_total": false}, {"name": "stop_count_first_month", "alias": "stop_count_first_month", "aggregation": "count", "column": "no", "percentage_of_total": false}, {"name": "avg_duration_first_month", "alias": "avg_duration_first_month", "aggregation": "avg", "column": "thoi_luong_seconds", "percentage_of_total": false}], "having": [], "ranking": null, "derived_metrics": [], "time_comparison": null, "time_granularity": null, "sort": [{"column": "thoi_gian_bat_dau", "field": "thoi_gian_bat_dau", "direction": "asc"}], "limit": 20, "output": "table", "query_complexity": "simple", "clarification_question": null}`

## CQ-017 - COMPLEX_DECOMPOSITION_ERROR

- Question: Xác định máy có downtime cao nhất, sau đó lấy top nguyên nhân của máy đó.
- Notes: Non-executable plan: clarification
- Plan: `{"intent": "clarification", "tables": [], "joins": [], "filters": [], "dimensions": [], "metrics": [], "having": [], "ranking": null, "derived_metrics": [], "time_comparison": null, "time_granularity": null, "sort": [], "limit": 20, "output": "text", "query_complexity": "simple", "clarification_question": "Mình chưa có thực thể trước đó để tham chiếu. Bạn muốn chọn máy, nhóm hoặc nguyên nhân nào?"}`
