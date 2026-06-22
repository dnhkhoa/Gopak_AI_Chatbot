# File Upload And Ingestion Flow

Updated: 2026-06-22

## Flow

1. `POST /api/files/upload` accepts one `.xlsx`.
2. Backend validates extension and MIME.
3. Raw file is saved to `data/uploads/{file_id}.xlsx`.
4. Metadata is written atomically to `data/uploaded_files.json` with `status=uploaded`.
5. Backend computes SHA-256.
6. Backend scans workbook sheets through the existing ingestion scanner.
7. Backend normalizes rows and writes parquet under `cache/tables`.
8. Backend rebuilds `cache/data_catalog.json`.
9. Backend validates query readiness with DuckDB and provenance checks.
10. Metadata becomes `status=ready`, `queryable=true`, `progress=100`.

If ingestion fails after the raw file is saved, metadata remains visible with:

- `status=failed`
- `queryable=false`
- `processing_stage=failed`
- structured `error.code` and `error.message`

## Delete Flow

`DELETE /api/files/{file_id}`:

1. Marks metadata `deleting`.
2. Clears active file references in conversations.
3. Removes uploaded parquet/cache manifest entries.
4. Rebuilds the catalog.
5. Deletes the raw upload.
6. Removes metadata record.

## Restart Reconciliation

On FastAPI startup, `FileLifecycleService.reconcile_uploaded_files(auto_retry=True)` checks uploaded metadata against raw files, cache, catalog, DuckDB readability, and provenance. Records that were interrupted in `uploaded` or `processing` can be retried without a manual script.
