# Web Migration Audit

Updated: 2026-06-21

## Current Streamlit Entry Points

`app.py` is now a legacy fallback UI. Before migration it directly owned the orchestration path:

- Load or ingest catalog.
- Create and load `ConversationMemoryService`.
- Create conversation and persist turns.
- Call `QueryPlanner.plan(...)`.
- Call `SafeQueryExecutor.execute(...)`.
- Build Plotly chart through `build_chart(...)`.
- Build presentation through `build_presented_response(...)`.
- Export HTML/XLSX reports.
- Update `ConversationState` from plan/result.
- Save assistant turn and result parquet reference.

After migration, `app.py` calls `ChatApplicationService` and no longer directly calls planner, executor, SQL builder, or exporter.

## Reused Core Layers

- `src/catalog/`: workbook profiling, catalog load, relationship detection.
- `src/ingestion/`: dynamic Excel discovery, header detection, normalization, parquet cache.
- `src/routing/`: hybrid route decision and execution metadata.
- `src/query_understanding/`: deterministic planner, semantic matching, metric/dimension/filter/time/top-N detection.
- `src/llm/`: Ollama/Qwen planner and prompt/schema handling.
- `src/query/`: QueryPlan schema, validation, SQL builder, DuckDB executor, result validator.
- `src/conversation/`: durable state, state merger, reference resolver, turn classification, SQLite-backed memory service.
- `src/persistence/`: SQLite migrations/store and parquet result cache.
- `src/rendering/`: display formatting, presentation model, chart/report/export logic.
- `evaluation/` and `tests/`: existing evaluation and regression coverage.

## New Shared Boundary

`src/application/chat_service.py` is the shared application layer for both Streamlit and FastAPI.

`ChatApplicationService.process_message(...)` handles:

1. Load conversation state.
2. Save user turn.
3. Route/build/validate plan through the existing planner.
4. Execute generated DuckDB SQL through the existing safe executor.
5. Build presentation.
6. Export report artifacts when requested.
7. Update conversation state from plan/result.
8. Save assistant turn and parquet result reference.
9. Return a frontend-safe `ChatResponse`.

## Frontend-Safe Serialization

The service never returns pandas DataFrame or Plotly Python objects. It serializes:

- `table.columns` and `table.rows`.
- `chart.type`, `chart.x_key`, `chart.y_keys`, and `chart.data`.
- `downloads` as artifact IDs, never local file paths.
- `sources` as sanitized workbook/sheet names, not absolute paths.
- `metadata` only inside the API payload and hidden in the React UI unless debug is enabled.

## Streamlit Session State Keys

Legacy `app.py` keeps only:

- `conversation_id`
- `messages`

The previous UI-specific `conversation_state` and direct catalog/session orchestration are no longer required in Streamlit.

## Business Logic Removed From Streamlit

Moved to `ChatApplicationService`:

- planner construction/call
- DuckDB execution
- chart/presentation assembly
- report export
- state update
- turn persistence
- artifact registration by id

Still in Streamlit:

- CSS and fallback rendering only.
- Conversation selection convenience.
- Local `st.download_button` wrapping service artifact IDs.

## Remaining Legacy Surface

Streamlit is intentionally kept as fallback while the React + FastAPI app matures. It is not deleted and still runs independently at port 8501.
