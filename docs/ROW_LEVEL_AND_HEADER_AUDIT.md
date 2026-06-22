# Row-Level And Header Audit

Updated: 2026-06-22

## Sample File Availability

Requested sample file:

`Operation_Downtime_20251212_101824 (2)(1).xlsx`

Audit result: this file was not present in the workspace, `data/uploads`, or under `D:\` during this run. The implementation and benchmark runners therefore prefer that file when available, but current artifacts were generated against the available fallback workbook:

`Machine_Downtime_20260203_100753.xlsx`

## Baseline Before Changes

The previous ingestion path:

- Scanned only the first 100 rows.
- Chose the highest scoring non-empty row using a simple score based on non-empty cells, uniqueness, text-like cells, and next-row density.
- Did not explicitly reject metadata rows such as `From time`, `To time`, `Reporter`, or `Total results`.
- Detected `Machine_Downtime_20260203_100753.xlsx / Report` header at Excel row 35.
- Detected candidate columns `D:M`, because the header row had a trailing garbage value after `Note`.
- Dropped both `Note` and the garbage column because both were all-null/near-empty.
- Persisted `_source_file`, `_source_sheet`, `_source_row`, and `_import_id`.
- Did not persist `_source_file_id`, `_source_file_name`, `_source_excel_row`, `_source_header_row`, `_data_row_index`, or `_record_no`.
- Treated `No.` as a normal business column, not a separate record-number concept.
- Date filtering in the analytical planner used start-time `date_between`, not interval overlap.
- Duration aggregation used parsed duration text in `thoi_luong_seconds`; it did not preserve reported/calculated/difference columns.
- Duplicate and overlap flags were not persisted.
- Operating-time questions could route ambiguously through normal planning.

Baseline fallback workbook facts:

- Header row: 35.
- First data row: 36.
- Last data row: 9186.
- Normalized rows: 9,151.
- Previous profile columns after drops: 13.

## After Changes

Header detection now:

- Scans at least 200 rows.
- Scores candidate header rows by non-empty cells, text ratio, unique ratio, contiguous columns, semantic names, following-row density, and consecutive valid records.
- Rejects metadata-like key/value rows.
- Detects repeated headers and footer/total rows.
- Keeps business columns such as `Note` even when all values are null.
- Drops only blank/numeric artifact columns outside the table.
- Stores header confidence and evidence.

Fallback workbook after-change facts:

- Header row: 35.
- First data row: 36.
- Last data row: 9186.
- Source columns: D:L.
- Normalized rows: 9,151.
- Garbage columns included: 0.

Persisted provenance fields:

- `_source_file_id`
- `_source_file_name`
- `_source_sheet`
- `_source_excel_row`
- `_source_header_row`
- `_data_row_index`
- `_record_no`
- `_import_id`

Duration fields:

- `duration_reported_text`
- `duration_reported_seconds`
- `duration_calculated_seconds`
- `duration_difference_seconds`
- `duration_anomaly`
- `duration_seconds`

Data-quality fields:

- `_is_exact_duplicate`
- `_duplicate_group_id`
- `_duplicate_group_size`
- `_overlaps_same_machine`

## Remaining Audit Notes

- The requested Operation workbook oracle could not be verified because the file was not available.
- Current row-level runtime uses a deterministic service layer over the selected-file parquet. It enforces active file scope but does not yet represent all row-level operations as first-class SQL `QueryPlan` variants.
- Analytical date filters still use start-time filters in the generic planner. Row-level date/time questions use interval overlap.
