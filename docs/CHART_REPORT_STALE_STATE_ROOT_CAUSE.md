# Chart/Report Stale State Root Cause

## Baseline Failure

The 8-turn baseline in `artifacts/chart_report_stale_state_baseline.json` showed stale plan reuse:

- A new chart request such as "xu hướng downtime theo ngày" was routed as an output change instead of a new analytical request.
- The state merger reused the previous machine ranking plan, so later chart/report turns inherited old dimensions, metrics, filters, and chart type.
- Report requests were treated as single-result presentation changes, not as multi-section report orchestration.
- Chart payloads used raw duration seconds while table/narrative rendered human-readable duration units.
- Follow-up commentary used a broad LLM prompt over a summary object, so answers could drift from the visible result.

## Root Cause

The turn classifier only recognized a self-contained ranking query as `NEW_QUERY`. Self-contained chart/report requests were classified as `CHANGE_OUTPUT`, which allowed `restore_topic_plan` and prior conversation state to mutate the last query plan instead of building a fresh plan.

The chart layer did not validate that the selected dimension, metric, chart type, and result source matched the current request. The report layer exported the last query result instead of creating independent overview/KPI/ranking/trend sections.

## Fix

- Added `RequestContract` and `ChartContract` with per-turn lineage ids:
  `turn_id`, `request_contract_id`, `query_plan_id`, `query_result_id`, `answer_brief_id`, `chart_spec_id`, and `report_artifact_id`.
- `NEW_REQUEST` turns explicitly reset inherited analytical state before planning.
- Complete chart/report requests are now classified as new requests unless they explicitly reference the previous result.
- Added deterministic planning for time-series charts, distribution/share charts, and downtime share metrics.
- Added request coverage metadata so requested dimensions, metrics, outputs, chart types, and time grain are checked against the plan.
- Chart payloads normalize duration values to display units and attach a chart contract with current-turn source ids.
- Report requests now use multi-query orchestration with overview, KPI, top machines, top causes, trend, commentary, source, and limitation sections plus HTML/XLSX downloads.
- Follow-up commentary over "kết quả trên" now reads the cached visible result and uses deterministic grounded commentary instead of an open-ended LLM response.

## Regression Coverage

New regression artifacts:

- `artifacts/chart_request_fulfillment_results.json`
- `artifacts/report_orchestration_results.json`
- `artifacts/conversation_state_contamination_results.json`
- `artifacts/chart_report_manual_uat.json`

All new chart/report/state contamination benchmark failures must remain zero.
