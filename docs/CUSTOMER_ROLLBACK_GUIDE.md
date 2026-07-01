# Customer Rollback Guide

Rollback is supported by restoring the previous Git revision and the previous `cache/manifest.json` and `cache/data_catalog.json` from backup.

Procedure:

1. Stop backend and frontend.
2. Restore previous application revision.
3. Restore previous cache manifest/catalog backup.
4. Run `python scripts_ingest.py`.
5. Start backend and frontend.
6. Run `/api/health` and smoke chat questions.

This audit did not execute a real rollback drill. See `artifacts/ROLLBACK_EXECUTION_LOG.md`.
