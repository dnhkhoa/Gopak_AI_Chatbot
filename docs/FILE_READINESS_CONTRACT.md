# File Readiness Contract

Updated: 2026-06-22

`Ready` means the file is queryable, not merely uploaded.

A file can be `ready` only when all checks pass:

- Raw upload exists.
- Metadata SHA-256 matches raw file bytes.
- Ingestion produced at least one table.
- Parquet cache exists and is readable.
- Catalog contains at least one table with the uploaded `file_id`.
- DuckDB `COUNT(*)` succeeds for every scoped parquet table.
- Every scoped parquet table has `_source_file_id`.
- `_source_file_id` equals the selected file id for every row.
- Total queryable row count is greater than zero.

Status values:

- `uploaded`: raw file saved, ingestion not finished.
- `processing`: ingestion/readiness validation running.
- `ready`: queryable and selectable.
- `failed`: ingestion/readiness failed; not selectable.
- `deleting`: delete cleanup in progress; not selectable.

Frontend should treat only `status=ready && queryable=true` as selectable.
