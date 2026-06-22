# Row-Level Query Architecture

Updated: 2026-06-22

## Scope

Row-level query handling is implemented as a deterministic layer in `ChatApplicationService` after active-file preflight and before generic metadata/planner routing.

Flow:

1. Conversation active file is required.
2. `get_catalog_for_file(active_file_id)` returns only selected-file tables.
3. `try_row_level_response(...)` receives the scoped catalog and state.
4. The selected table parquet is read.
5. Deterministic record/date/time/data-quality logic returns a typed `ChatResponse`.
6. If no row-level intent matches, the request continues to existing customer-intent and planner flow.

## Supported Distinctions

- `No 1`, `record number 1`, `ban ghi so 1` -> `_record_no = 1`.
- `ban ghi dau tien sau header`, `dong du lieu thu 100` -> `_data_row_index`.
- `hang Excel 36` -> `_source_excel_row`.
- `gan nhat`, `som nhat` -> datetime ordering, not row order.
- Machine/day/window questions -> interval overlap.
- Operating-time questions -> clarification, because downtime data alone cannot prove running time.

## Interval Policy

Row-level date/time filters use:

```text
event_start < window_end
AND event_end >= window_start
```

This includes cross-midnight intervals that started before the requested day but overlap it.

For duration totals, the current row-level response uses reported event duration and records:

```text
duration_policy = reported_duration_seconds
```

Clipped per-day duration is identified as a remaining enhancement for analytical totals.

## Duplicate And Overlap Policy

Ingestion does not delete duplicates.

It persists:

- `_is_exact_duplicate`
- `_duplicate_group_id`
- `_duplicate_group_size`

For overlap detection on the same machine, it persists:

- `_overlaps_same_machine`

The response layer distinguishes raw record count from deduplicated event count in metadata and benchmark artifacts.

## Safety

The row-level layer preserves the file-scope contract:

- No active file means no row-level query.
- It reads only the selected-file parquet.
- Operating-time inference is refused/clarified unless the user confirms assumptions.
- It does not call the LLM.
- It does not generate raw SQL.
