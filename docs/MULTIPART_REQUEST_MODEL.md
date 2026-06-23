# Multi-Part Request Model

Date: 2026-06-23

Gopak already has a structured request representation (`QueryPlan` in `src/query/schemas.py`)
produced by the deterministic detector stack. Rather than add a parallel `AnalyticsRequest`
model, multi-part capability is expressed through that pipeline plus presentation modifiers.
Field names differ from the spec sketch but capability is equivalent.

## Capability mapping

| Spec concept | Where it lives | Notes |
| --- | --- | --- |
| `intent` | `QueryPlan.intent` (`query` / `chart` / `dashboard` / `report`) | from `detect_operation` / merge |
| `dimension` | `QueryPlan.dimensions` | `detect_dimension` (catalog role columns) |
| `metrics` / `aggregation` | `QueryPlan.metrics[].aggregation/column` | `detect_metric`; `count`/`sum`/`avg`/`count_distinct` |
| `filters` | `QueryPlan.filters` | `parse_filters` |
| `time_range` | `QueryPlan.time_granularity` + date filters | `resolve_time` (e.g. "tháng gần nhất") |
| `ranking` / `limit` | `QueryPlan.sort` + `QueryPlan.limit` | `detect_topn` |
| `derived_metrics` (percentage) | `MetricSpec.percentage_of_total` | planner % branch |
| `requested_outputs` (table/chart) | `QueryPlan.output` | `detect_output` |
| `commentary_requested` | `_requests_commentary(message)` + `_generate_grounded_commentary` | commentary appended to the analytics response, grounded on the result |
| `chart_requested` / `table_requested` | `QueryPlan.output` + `build_chart` | |

## Example

> Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét.

resolves (Loss_Assignment) to:

```json
{
  "intent": "query",
  "dimensions": ["nhom_ton_that"],
  "metrics": [{"aggregation": "count", "name": "row_count", "percentage_of_total": true}],
  "sort": [{"column": "row_count", "direction": "desc"}],
  "limit": 5,
  "output": "table"
}
```

plus `commentary_requested = true` → 1–3 grounded observations appended (top group, share %, gaps).

## Precedence guarantee

Output/commentary modifiers never override the core analytical request. A trailing
"và nhận xét" / "và vẽ biểu đồ" adds a presentation layer; it does not turn the turn into a
follow-up-only commentary request. Follow-up-only commentary ("nhận xét bảng vừa rồi") is detected
by the absence of a new analytical request and/or an explicit reference to the prior result.

## Guardrails (unchanged)

LLM (commentary + semantic resolver) returns narrative only — never SQL, never new numbers,
never a different source file, never silently dropping requested parts. Numbers in commentary are
grounded on the validated result.
