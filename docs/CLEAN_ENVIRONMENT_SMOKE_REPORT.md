# Clean Environment Smoke Report

Generated: 2026-06-24T03:55:20.153613+00:00

## Summary

- Status: `passed`
- Commit tested in clean clone: `f5c96c6`
- Clone root: `D:\Gopak-Clean-Smoke-f5c96c6`
- Uploaded files: 3
- Downloaded report artifacts: 2

## Steps

| Step | Result |
| --- | --- |
| backend_health_initial | passed |
| upload_three_excel_files | passed |
| conversation_persistence_after_restart | passed |
| context_refinement_sequence | passed |
| entrytransaction_about_phrase | passed |
| report_downloads | passed |

## Notes

- The smoke run used a fresh clone, fresh Python venv, fresh `npm --prefix frontend ci`, and empty `data/`, `cache/`, and `reports/` directories.
- Three Excel files were uploaded through `/api/files/upload`; no pre-existing upload registry or table cache was reused.
- The API sequence covered Vietnamese-accented context refinement, EntryTransaction `ve luong xe` phrasing, report export downloads, and backend restart persistence.
