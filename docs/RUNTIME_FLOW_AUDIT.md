# Runtime Flow Audit

Updated: 2026-06-20

## Current Runtime Flow

1. Streamlit entry point: `app.py`
   - Loads settings with `src.config.get_settings()`.
   - Loads or rebuilds catalog with `ensure_catalog()` / `scripts_ingest.main()`.
   - Stores `ConversationState` and chat messages in `st.session_state`.
   - On a user question, constructs `QueryPlanner(catalog, settings)` and calls `planner.plan(question, state)`.

2. Pre-policy: `src.llm.planner.QueryPlanner._pre_policy`
   - Hard-coded phrase rules return `clarification` or `refusal`.
   - Handles some out-of-domain, vague ranking, and unsafe join phrases.
   - Risk: policy is embedded in planner and not represented as an explicit route decision.

3. Schema linking: `src.llm.prompts.select_catalog_context`
   - Scores tables and columns using keyword/role/fuzzy signals.
   - Sends at most two tables to the LLM prompt.
   - Writes `artifacts/planner_context_samples.json`.
   - Risk: selected context can still include both downtime and loss-assignment tables for simple deterministic questions.

4. REAL_LLM planner: `src.llm.planner.QueryPlanner.plan`
   - If Ollama health is OK, calls `OllamaClient.chat(..., format_schema=QueryPlan.model_json_schema())`.
   - Normal path parses with `json.loads(raw)` in `_coerce_plan_json`.
   - LLM never generates SQL.

5. Repair retry: `src.llm.planner.QueryPlanner.plan`
   - On any exception from parse/coerce/Pydantic/validation, retries once with validation error and previous response.
   - If retry fails and `enable_heuristic_fallback=True`, falls through into heuristic planning.

6. Heuristic fallback: `src.llm.planner.QueryPlanner._heuristic_plan`
   - Local rule-based plan generator.
   - Currently triggered when Ollama is unavailable, when LLM/retry fails, or in evaluation when the base URL is forced invalid.
   - Risk: it can silently substitute a plausible-looking query after LLM failure.

7. Validator: `src.query.validator.PlanValidator`
   - Checks table/column existence, metric sort aliases, aggregation type for numeric/duration, and relationship allowlist.
   - `clarification` and `refusal` bypass query validation.
   - Gaps: category value existence, date/numeric filter type, top-N shape, output/result shape.

8. SQL builder: `src.query.sql_builder.SQLBuilder`
   - Builds SELECT-only SQL from `QueryPlan`.
   - Uses quoted identifiers and parameterized filters.
   - Adds default ordering by first metric unless time granularity is present.
   - Risk: no explicit SQL provenance object; builder assumes it only receives validated plans.

9. DuckDB executor: `src.query.executor.SafeQueryExecutor`
   - Validates again, builds SQL, executes against parquet through DuckDB.
   - Current connection uses in-memory DuckDB with `read_only=False`.
   - Risk: connection is not explicitly read-only, and there is no result validation after fetch.

10. Presentation renderer: `src.rendering.presentation.build_presented_response`
    - Converts query result to scalar/table/chart/report/clarification/error presentation.
    - Treats `refusal` as error-like presentation.
    - Risk: table summary always phrases first row as "highest", even if ordering is ascending or chronological.

11. Conversation state: `src.conversation.state.ConversationState`
    - Stores active tables, filters, dimensions, metrics, and last output.
    - Updated only after executable query.
    - Risk: no explicit state machine for refine/change/reset/reference operations.

12. Evaluation flow: `evaluation.run_evaluation`
    - Generates 85 cases.
    - Runs REAL_LLM with `enable_heuristic_fallback=False`.
    - Runs fallback benchmark by forcing Ollama unavailable and `enable_heuristic_fallback=True`.
    - Writes after-fix artifacts.
    - Risk: final console print can crash on Windows cp1252 after artifacts are written.

## Fallback Triggers

- `QueryPlanner.plan` reaches heuristic fallback when:
  - Ollama health is not OK and `ENABLE_HEURISTIC_FALLBACK=true`.
  - LLM structured output fails, retry fails, and `ENABLE_HEURISTIC_FALLBACK=true`.
- Evaluation intentionally uses fallback by replacing Ollama base URL with `http://127.0.0.1:9`.

## Silent Fallback Assessment

- Silent fallback exists in runtime when `ENABLE_HEURISTIC_FALLBACK=true`.
- The UI only receives `planned.used_fallback` in debug timings, and normal users see a normal answer.
- There is no production-safe distinction between deterministic planning and legacy fallback.

## Execution Metadata Today

- `PlannerResult.metadata` exists with strings like `pre_policy`, `real_llm`, `real_llm_failed`, `heuristic_fallback`, `unavailable`.
- Metadata is not a typed contract and does not include required fields such as `execution_mode`, `router_confidence`, `routing_reason`, `llm_called`, `llm_call_count`, or phase latency.
- Streamlit debug shows plan, SQL, and basic timings, but not a full execution trace.

## Risky Locations

- `app.py`: executes every non-clarification plan; `refusal` is not explicitly blocked before executor.
- `src.llm.planner.QueryPlanner.plan`: LLM failure can silently fall through into heuristic fallback.
- `src.llm.planner._heuristic_plan`: defaults to table/metric/duration choices for broad questions.
- `src.llm.planner._date_filter`: data-relative dates were hard-coded instead of derived from catalog.
- `src.query.validator.PlanValidator`: does not validate category values or filter datatype compatibility.
- `src.query.executor.SafeQueryExecutor`: no post-query result validation and no explicit read-only connection.
- `src.rendering.presentation._table_summary`: may describe a result as highest when the sort is not descending.

## Latency Hotspots

- Runtime calls Ollama before deterministic parsing for clear analytics questions.
- `OllamaClient.health()` is called inside each planner request.
- REAL_LLM P95 is about 17.4 seconds after Round 1.
- Report and Excel export happen on every executable runtime answer, even when the user did not ask for report/export.
- Evaluation repeats full ingestion/catalog setup and multiple LLM calls.

## Runtime vs Evaluation Differences

- Runtime currently uses environment default `ENABLE_HEURISTIC_FALLBACK`, which was `true` in `.env.example`.
- REAL_LLM evaluation disables heuristic fallback, while fallback benchmark forces Ollama unavailable.
- Runtime exports HTML and Excel for every executable answer; evaluation builds presentation but does not export files.
- Evaluation catches exceptions as failure rows; runtime shows a generic Streamlit error.

## Planned Changes

- Add typed execution modes: `DETERMINISTIC`, `REAL_LLM`, `CLARIFICATION`, `REFUSAL`, `SAFE_FAILURE`, `LEGACY_FALLBACK`.
- Default `ENABLE_HEURISTIC_FALLBACK=false` and gate legacy fallback behind `FORCE_LEGACY_FALLBACK_MODE=true`.
- Add hybrid router before LLM calls.
- Add deterministic parser for high-confidence analytics questions.
- Add data-derived temporal resolver.
- Add semantic candidate matcher with database-backed allowed values and debug artifact.
- Add response metadata/tracing and UI debug display.
- Block SQL for clarification/refusal/safe failure.
- Fix Windows stdout encoding in evaluation.
- Add hybrid evaluation artifacts separate from legacy fallback benchmark.
