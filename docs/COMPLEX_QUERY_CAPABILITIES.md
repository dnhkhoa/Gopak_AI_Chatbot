# Complex Query Capabilities

Updated: 2026-06-21

## Implemented

- Multiple metrics in one grouped query:
  - total downtime
  - row count / number of stops
  - average duration
- Percentage/share of total:
  - `metric * 100 / SUM(metric) OVER ()`
  - guarded with `NULLIF(..., 0)`
- Above-average grouped filters:
  - aggregate CTE
  - compare grouped metric against `AVG(metric)` over grouped rows
- Windowed Top-N:
  - aggregate CTE
  - `ROW_NUMBER()/RANK()/DENSE_RANK() OVER (PARTITION BY ... ORDER BY ...)`
  - optional `_rank <= top_n`
- Complex deterministic routing:
  - complex questions can remain `execution_mode=DETERMINISTIC`
  - metadata includes `query_complexity`
- Structured state-based follow-ups:
  - change output
  - change time
  - add/remove filters
  - change metric/dimension/ranking
  - resolve top machine/loss/group from structured result summary

## QueryPlan Extensions

- `MetricSpec.percentage_of_total`
- `QueryPlan.having`
- `QueryPlan.ranking`
- `QueryPlan.derived_metrics`
- `QueryPlan.time_comparison`
- `QueryPlan.query_complexity`

LLM still does not produce SQL. SQL is generated only from validated QueryPlan objects.

## Remaining Gaps

- Long combined queries with many simultaneous operations can still drop part of the request.
- Period comparison is not fully modeled yet.
- Nested two-step query pipelines are not first-class yet.
- Multi-turn automated accuracy is below the acceptance target.

## Round 3 Evaluation

- Complex queries: 16/20 passed.
- Percentage: 2/2 passed.
- Above-average filters: 2/2 passed.
- Windowed Top-N: 2/2 passed.
- Multi-turn: 11/15 passed.
- Persistence: 4/4 passed.
