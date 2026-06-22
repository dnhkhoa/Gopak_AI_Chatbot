# Evaluation Failures

## EVAL-041 - AGGREGATION_ERROR

- Category: typo
- Mode: HEURISTIC_FALLBACK
- Question: may nao downtime cao nhat
- Expected: `{"records": [{"total_duration_seconds": 7162405.0}], "comparison_type": "numeric", "expected_behavior": ""}`
- Actual: `{"records": [{"may": "Máy 11", "total_duration_seconds": 1488867.0}]}`
- Planner JSON: `{"intent": "query", "tables": ["machine_downtime_20260203_100753_report_3c3f6d"], "joins": [], "filters": [], "dimensions": ["may"], "metrics": [{"name": "total_duration_seconds", "alias": "total_duration_seconds", "aggregation": "sum", "column": "thoi_luong_seconds", "percentage_of_total": false}], "having": [], "ranking": null, "derived_metrics": [], "time_comparison": null, "time_granularity": null, "sort": [{"column": "total_duration_seconds", "field": "total_duration_seconds", "direction": "desc"}], "limit": 1, "output": "table", "query_complexity": "simple", "clarification_question": null}`
- SQL: `SELECT "machine_downtime_20260203_100753_report_3c3f6d"."may" AS "may", sum("machine_downtime_20260203_100753_report_3c3f6d"."thoi_luong_seconds") AS "total_duration_seconds" FROM read_parquet(?) AS "machine_downtime_20260203_100753_report_3c3f6d" GROUP BY "machine_downtime_20260203_100753_report_3c3f6d"."may" ORDER BY "total_duration_seconds" DESC LIMIT 1`
- Exception: ``
- Notes: Numeric oracle comparison.
- Suggested fix: Add planner examples for aggregation/date constraints and validate metric aliases.
- Severity: Medium
