# Complex Query and Memory Audit

Updated: 2026-06-21

## Inputs Reviewed

- `docs/RUNTIME_FLOW_AUDIT.md`
- `docs/PROGRESS_EVALUATION.md`
- `artifacts/evaluation_summary_hybrid.md`
- `artifacts/evaluation_failures_hybrid.md`
- `artifacts/evaluation_results_hybrid.json`
- `artifacts/multiturn_state_traces.json`
- `app.py`
- `src/conversation/state.py`
- `src/query/schemas.py`
- `src/query/sql_builder.py`
- `src/query/validator.py`
- `src/query/executor.py`
- `src/query/result_validator.py`
- `src/query_understanding/*`
- `src/routing/*`
- `src/llm/planner.py`
- `src/rendering/presentation.py`

## Current QueryPlan Shape

`src/query/schemas.py` currently supports:

- `intent`: query, chart, dashboard, report, clarification, refusal, safe_failure.
- `tables`, `joins`, `filters`, `dimensions`, `metrics`, `time_granularity`, `sort`, `limit`, `output`, `clarification_question`.
- `MetricSpec`: one aggregation per metric: count, count_distinct, sum, avg, min, max, median.
- `FilterSpec`: row-level filters only, including equality, contains, in, numeric range, date_between, null checks.
- `SortSpec`: sort by column or metric alias.

Missing for complex analytics:

- Post-aggregation filters/HAVING.
- Windowed ranking with `PARTITION BY`.
- Percentage-of-total metrics.
- Derived metrics such as percentage change, difference, ratio.
- Time comparison model.
- Multi-step/nested query model.
- Query complexity metadata.

## Current SQL Builder Support

`src/query/sql_builder.py` builds one SELECT over `read_parquet(?)` with optional joins:

- Dimension projection.
- Time bucket via `date_trunc`.
- Aggregates: count, count distinct, median, sum, avg, min, max.
- WHERE filters.
- GROUP BY dimensions.
- ORDER BY explicit sort or default metric/time sort.
- LIMIT.

Unsupported:

- HAVING and group-average predicates.
- CTE/subquery pipelines.
- `SUM(metric) OVER ()` for share-of-total.
- `ROW_NUMBER() OVER (PARTITION BY ...)` for windowed top-N.
- Period comparison pivots or metric deltas.
- Nested entity analysis where one aggregate result feeds a second query.

## Current Validation and Execution

`src/query/validator.py` checks:

- Non-executable intents bypass validation.
- Tables and columns exist.
- Metric aliases can be sorted.
- Numeric/duration columns are required for sum/avg/median.
- Join columns exist and relationships have catalog evidence.
- Top-N scalar plans with `limit < 20` require a dimension.
- Filter type compatibility for date and range operators.

`src/query/executor.py` validates, builds SQL, rejects non-SELECT SQL, executes in DuckDB, and validates result shape.

Gaps:

- No validation for HAVING/ranking because schema does not yet contain them.
- No guard that derived metric aliases reference existing base metrics.
- Result validator assumes `len(df) <= plan.limit`, which is wrong for windowed top-N because total rows can exceed per-partition top-N.
- DuckDB connection is still `read_only=False` because the in-memory connection cannot be opened read-only.

## Current Conversation State

`src/conversation/state.py` is a dataclass stored in `st.session_state.conversation_state`.

Fields include:

- `active_table`, `active_tables`
- `active_metric`, `metrics`
- `active_dimensions`, `dimensions`
- `active_filters`, `active_time_range`, `time_range`
- `active_sort`, `active_limit`, `active_output`
- `last_entities`, `last_result_reference`, `last_plan`, `last_output`

`update_from_plan()` fills state after executable plans. `reset()` clears all analytical state.

Gaps:

- It is not Pydantic and has no `conversation_id`.
- No `active_having`, `active_ranking`, `last_result_summary`, `last_result_cache_id`, `recent_turn_ids`, or `conversation_summary`.
- It has compatibility aliases and older fields mixed together.
- `last_entities` is only updated from filters, not from top result rows.
- It is hot session state only; restart loses state.

## Current Streamlit Session State

`app.py` uses:

- `st.session_state.conversation_state`: one in-memory `ConversationState`.
- `st.session_state.messages`: user/assistant chat messages, including display records for the UI.
- `st.session_state.catalog`: loaded catalog.

Risks:

- Messages can contain display row records; this is acceptable as a UI hot cache but should not become the persistence layer.
- No `conversation_id`.
- No persistent conversation list.
- Streamlit code directly owns reset/delete behavior instead of going through a memory service.

## Current Follow-Up Merge Behavior

There is no explicit turn classifier or deterministic state merger.

Current inheritance happens indirectly:

- `DeterministicPlanner._select_table()` reuses active table only for phrases like `tren`, `do`, `ket qua`, `chi lay`, `ve top`, `giu`.
- Some follow-ups become new plans based on the old active table.
- `update_from_plan()` overwrites state only after executable plans.
- Clarifications do not merge any partial state.

Observed problems in `artifacts/multiturn_state_traces.json`:

- Time-only follow-up `Chỉ lấy tháng gần nhất` becomes clarification and does not merge a date filter.
- `last_entities` stays empty after ranking results, so `máy đó`, `nhóm đó`, and `nguyên nhân đứng đầu` cannot be resolved.
- Follow-up filters such as `Chỉ giữ các lần trên 1 giờ` can clarify instead of adding a duration filter.
- `Phân tích top nguyên nhân bên trong nhóm đó` keeps the previous group dimension instead of resolving the top group and switching to loss-name analysis.

## Why the 15 Multi-Turn Cases Are Manual

The current evaluation records state before/after and actual plan, but it has no automated oracle for:

- Turn type classification.
- Expected state changes.
- Entity references.
- Whether a filter/time/ranking change was merged rather than treated as a new query.
- Whether a NEW_QUERY correctly avoids inheriting old state.

Mode distribution in the current traces:

- 11 deterministic turns.
- 4 clarification turns.
- 0 turns with persisted structured entity references.

## Current Complex Failure Locations

From `artifacts/evaluation_failures_hybrid.md`:

- `EVAL-014` fails in SQL builder capability: global `ORDER BY ... LIMIT 20` is used instead of windowed top-N per month.
- `EVAL-015` fails in planner/schema/validator capability: above-average grouped filter is not representable, so LLM path returns invalid plan and the runtime safely fails.
- `EVAL-017` fails in planner/schema capability: percentage ranking is not representable, so it clarifies.
- `EVAL-041` is an oracle/ambiguity mismatch: the plan answers "which machine is highest", while the oracle expects scalar total downtime.

## Reusable Components

- `QueryPlan`, `MetricSpec`, `SortSpec`, `FilterSpec` provide a safe structured core.
- `PlanValidator`, `SafeQueryExecutor`, and generated SQL-only execution preserve safety.
- `DeterministicPlanner` already knows table/role columns and can be extended with small detectors.
- `time_resolver` already supports first/latest month and last two months.
- `EntityMatcher` already reads real category values and emits semantic debug artifacts.
- `ExecutionMetadata` can carry `query_complexity`, persistence state, and state merge traces.
- `build_presented_response()` can display multi-metric tables without large UI changes.

## Maintenance Risks Found

- `src/llm/planner.py` currently contains two `plan()` methods in the same class. Python uses the second definition, but this is confusing and should be cleaned up during planner work.
- Some files contain mojibake display strings from earlier encoding paths; these do not block backend behavior but make docs/UI harder to review.
- Result validator must change before windowed top-N, because total result rows can validly exceed `plan.limit` when limit is per partition.

## Minimal Fix Plan

1. Convert `ConversationState` to a Pydantic-compatible model while preserving current field names and call sites.
2. Add local SQLite persistence behind `ConversationMemoryService`, with Streamlit using the service and falling back to session-only mode on errors.
3. Add turn classifier, state merger, and reference resolver for deterministic multi-turn flows.
4. Add result cache references that store large results as parquet under `cache/conversations/<conversation_id>/<turn_id>.parquet`.
5. Extend QueryPlan with narrowly validated `having`, `ranking`, `derived_metrics`, and `query_complexity`.
6. Extend SQL builder for:
   - multiple metrics,
   - percentage-of-total,
   - group-average HAVING through CTE,
   - windowed top-N through aggregate CTE plus row_number.
7. Add deterministic detectors for the exact capability families, not full natural-language SQL.
8. Add tests and Round 3 artifacts before claiming readiness.

## Non-Goals for This Round

- No Redis, vector database, cloud storage, LangGraph memory, or arbitrary SQL/Python generation.
- No ingestion rewrite.
- No model change.
- No UI redesign.
- No raw Excel data or large DataFrames in SQLite.
