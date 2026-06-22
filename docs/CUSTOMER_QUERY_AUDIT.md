# Customer Query Audit

Updated: 2026-06-21

## Reproduced Bug

Request sent through the current Web API:

```text
POST /api/conversations/{id}/messages
message = "nội dung của data"
debug = true
```

Actual behavior before the fix:

- `response_type`: `scalar`
- `execution_mode`: `DETERMINISTIC`
- generated SQL: `SELECT sum(...thoi_luong_seconds) AS total_duration_seconds ...`
- answer: `1.989,56 giờ`

This is a default downtime false positive.

## Root Cause

The failure happens before DuckDB execution:

1. `src/query_understanding/operation_detector.py`
   - Returns `query` with confidence `0.85` as a default for every question that is not chart/dashboard/report.

2. `src/query_understanding/deterministic_planner.py`
   - `_select_table(...)` returns Machine Downtime as the fallback table when no specific table is detected.

3. `src/query_understanding/metric_detector.py`
   - The broad rule containing `thoi gian`, `thoi luong`, `dung`, `dt`, `tong`, `bao lau`, `bao nhieu gio` defaults to `sum(duration)`.
   - When a question is vague, the planner still has a table and can still construct an analytical plan.

4. `src/routing/router.py`
   - High-confidence deterministic candidates are accepted and routed to SQL execution.
   - Low-context questions are not explicitly classified as data overview/schema/sample/quality.

The SQL builder/executor are not the root cause. They execute a validated but semantically wrong `QueryPlan`.

## Existing Intents

`QueryPlan.intent` currently supports:

- `query`
- `chart`
- `dashboard`
- `report`
- `clarification`
- `refusal`
- `safe_failure`

Execution modes currently represented in metadata include:

- `DETERMINISTIC`
- `REAL_LLM`
- `CLARIFICATION`
- `REFUSAL`
- `SAFE_FAILURE`
- `LEGACY_FALLBACK`

## Missing Customer Intents

The customer-facing layer lacked first-class handling for:

- `DATA_OVERVIEW`
- `TABLE_OVERVIEW`
- `SCHEMA_INSPECTION`
- `SAMPLE_ROWS`
- `DATA_RANGE`
- `DATA_QUALITY`
- `EXPORT_REQUEST` separate from report intent
- broad `CONVERSATION_FOLLOWUP`

## Default Downtime Locations

- `src/query_understanding/deterministic_planner.py::_select_table`
  - Falls back to Machine Downtime.
- `src/query_understanding/metric_detector.py::detect_metric`
  - Falls back to sum duration for broad downtime/time terms.
- `src/llm/planner.py::_heuristic_plan`
  - Legacy fallback also chooses a table and metric when enabled.

## Low-Confidence Table Selection

`DeterministicPlanner._select_table` always returns a table unless the catalog is missing. This means the router often receives a plan-shaped candidate rather than a true unresolved state.

## Frontend/API/Application Flow

Current web path:

```text
React
  -> FastAPI /api/conversations/{id}/messages
  -> ChatApplicationService.process_message
  -> QueryPlanner.plan
  -> HybridRouter / DeterministicPlanner / LLM planner
  -> SafeQueryExecutor
  -> presentation + ChatResponse
```

The frontend and API use the same `ChatApplicationService`; evaluation must use the same service to avoid testing a different pipeline.

## Runtime vs Evaluation

Hybrid evaluation artifacts use `QueryPlanner`/executor/presentation directly in evaluation scripts. The new customer runner must call `ChatApplicationService` to match the web runtime.

## Overfit Risk

The old 85-case suite is strong on known downtime analytics, but weak on customer discovery questions. It rewards default downtime answers because many cases are downtime-centric. Missing categories include overview/schema/sample/data quality and broad natural questions such as `data có gì`.

## Fix Strategy

- Add a customer intent classifier before analytical planning in `ChatApplicationService`.
- Handle overview/schema/sample/range/quality from the catalog and metadata without analytical SQL.
- Require analytical questions to provide enough signal for metric/table/dimension; otherwise route to clarification.
- Keep old analytical query pipeline intact.
- Add regression assertions that unresolved/overview questions do not generate `SUM(duration)` SQL.

## After-Fix Verification

The root question now returns a catalog overview through the Web API:

- question: `nội dung của data`
- `response_type`: `data_overview`
- `execution_mode`: `DATA_OVERVIEW`
- generated SQL: `null`
- default downtime false positive: no

Customer evaluation results:

| Set | Passed | Total | Accuracy |
| --- | ---: | ---: | ---: |
| Development | 128 | 130 | 98.5% |
| Holdout | 44 | 50 | 88.0% |
| Total | 172 | 180 | 95.6% |

Default downtime false positives across all 180 customer cases: 0.
