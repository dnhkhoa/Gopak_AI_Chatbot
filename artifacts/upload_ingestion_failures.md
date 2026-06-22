# Upload Ingestion Failures

Expected failure behavior:

- Unsupported extension or MIME returns HTTP 400 and no file record is created.
- Workbook/read/header/parquet/catalog/readiness failures keep a metadata record with `status=failed`, `queryable=false`, `processing_stage=failed`, and a structured `error.code` / `error.message`.
- Conversations cannot select files that are `uploaded`, `processing`, `failed`, `deleting`, or `ready` but not `queryable`.
- If a selected file is deleted, active file references are cleared before raw/cache/metadata removal.

Observed during implementation:

- Legacy route marked `.xlsx` as Ready immediately after `pd.ExcelFile` opened.
- Existing files were reconciled into queryable records with file-scoped parquet/catalog entries.
- A timed-out reconciliation can leave `processing`; rerunning `process_file(..., force=False)` resumes from metadata/cache and restores `ready` once validation passes.
