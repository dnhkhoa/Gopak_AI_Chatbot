# Upload Ingestion Audit

Updated: 2026-06-22

## Finding

The previous upload route treated `Ready` as "pandas can open this workbook".

Old behavior in `backend/api/routes_files.py`:

- Save raw file under `data/uploads/{uuid}.xlsx`.
- Write metadata with `status=processing`.
- Open `pd.ExcelFile(destination)`.
- Set `status=ready`.

That path did not run workbook scanning, header detection, normalization, parquet writing, catalog rebuild, DuckDB validation, or provenance checks. A user could select a file marked Ready even though the query layer had no scoped table for that file.

## Fix

Upload lifecycle is now centralized in `src/files/lifecycle.py`.

The route delegates to `FileLifecycleService.upload()`, which moves a file through:

`uploaded -> processing -> ready | failed`

Processing stages:

- `file_validation`
- `sheet_scanning`
- `parquet_write`
- `catalog_update`
- `query_validation`
- `ready`

## Existing Files Baseline

Before changing file statuses, the three existing uploaded records were audited and written to `artifacts/existing_files_readiness.json`.

After reconciliation, all three records are queryable:

- `EntryTransaction_20260203_164943.xlsx`: 1,294 rows.
- `Loss_Assignment_20260203_100840.xlsx`: 36,309 rows.
- `Machine_Downtime_20260203_100753.xlsx`: 9,151 rows.

## Artifacts

- `artifacts/upload_ingestion_audit.json`
- `artifacts/existing_files_readiness.json`
- `artifacts/query_readiness_checks.json`
- `artifacts/restart_reconciliation.json`
- `artifacts/upload_ingestion_failures.md`
