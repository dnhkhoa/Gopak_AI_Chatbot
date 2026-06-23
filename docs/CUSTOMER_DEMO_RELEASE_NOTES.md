# Customer Demo Release Notes

## Status

`READY_FOR_CUSTOMER_DEMO`

## What Changed

- Fixed file selection latency by avoiding forced full Excel re-ingestion during active-file selection.
- Reloaded catalog from cache/disk after uploads so newly uploaded workbooks can be selected without restarting.
- Improved routing so high-confidence deterministic plans are not unnecessarily sent to Ollama.
- Tightened chart detection to avoid treating every `ve` token as a chart request.
- Added file-scoped failure inventory, challenge benchmark, black-box UAT, and workbook generalization checks.

## Verification Summary

- File-scoped benchmark: 320/320.
- Customer challenge benchmark: 150/150.
- Black-box UAT: 6/6, critical failures 0.
- New workbook generalization: 3/3.
- Backend pytest: 64/64.
- Frontend Vitest: 18/18.
- Frontend production build: pass.

Primary release gate artifact: `artifacts/customer_release_gate.md`.
