# File-Scoped Query Architecture

Updated: 2026-06-22

## Audit Before The Change

The previous runtime was multi-file by default:

- `ChatApplicationService.process_message()` loaded `self.get_catalog()` before any conversation/file decision.
- Metadata responders, `QueryPlanner`, `SafeQueryExecutor`, chart rendering, and source rendering all received the full catalog.
- Runtime catalog inspection showed 3 tables loaded at once:
  - `EntryTransaction_20260203_164943.xlsx / Report`
  - `Loss_Assignment_20260203_100840.xlsx / Report`
  - `Machine_Downtime_20260203_100753.xlsx / Report`
- The frontend file panel kept only local `selectedId` for opening details. It did not call the backend and did not affect planning or SQL execution.

That means a data overview could list all files, and planner table choice could switch across files based on question text.

## Active File Contract

Each conversation now has active file state in `ConversationState`:

- `active_file_id`
- `active_file_name`
- `file_contexts`
- `topic_frames`
- `current_topic`

The backend exposes:

`PUT /api/conversations/{conversation_id}/active-file`

Request:

```json
{"file_id": "..."}
```

Response:

```json
{
  "conversation_id": "...",
  "active_file_id": "...",
  "active_file_name": "Machine_Downtime_20260203_100753.xlsx",
  "status": "ready"
}
```

## Enforcement

`ChatApplicationService.process_message()` now runs a file-scope preflight before metadata routing, planning, or SQL:

- No active file: returns `clarification`, `generated_sql=null`.
- Active file missing: clears selection, returns `clarification`, `generated_sql=null`.
- Active file not Ready: returns `error`/safe failure, `generated_sql=null`.
- Question mentions another uploaded file: returns `refusal`, `generated_sql=null`.
- Active file is valid: builds `get_catalog_for_file(file_id)` and passes only that catalog to metadata responders, planner, executor, chart builder, formatter, and source renderer.

The service also validates that executable `plan.tables` is a subset of selected-file tables before calling DuckDB.

Every response metadata now includes:

- `active_file_id`
- `active_file_name`
- `file_scope_validated`

Debug responses include `scoped_catalog_tables`.

## Frontend Behavior

The React file panel now uses backend active-file state:

- Clicking a Ready file calls the active-file endpoint.
- The selected file is highlighted.
- The composer shows `Using: <filename>`.
- Conversation reload restores `active_file_id` and `active_file_name`.
- Deleting the selected file clears local UI selection; backend also clears stale state on next conversation/query load.
- There is no auto-select.

## Smoke Proof After The Change

Runtime smoke checks:

- No file selected + `noi dung cua data`:
  - `response_type=clarification`
  - `execution_mode=CLARIFICATION`
  - `generated_sql=None`
- Select `Machine_Downtime_20260203_100753.xlsx` + `noi dung cua data`:
  - `response_type=data_overview`
  - table rows: 1
  - `active_file_name=Machine_Downtime_20260203_100753.xlsx`
  - `file_scope_validated=True`
- Select Machine_Downtime + ask `hoi ve Loss_Assignment`:
  - `response_type=refusal`
  - `execution_mode=REFUSAL`
  - `generated_sql=None`

## Current Limitations

- File-scoped topic memory now preserves/restores per-file analysis context, but deeper A/B/A topic restoration still needs stronger semantic topic matching.
- Cross-file blocking is conservative and alias-based.
- Benchmark results show multipart and context sequences are not production-ready yet.
