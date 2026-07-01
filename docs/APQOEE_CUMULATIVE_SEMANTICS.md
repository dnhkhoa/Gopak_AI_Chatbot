# APQOEE Cumulative Semantics

`Cup3.xlsx` is APQOEE cumulative snapshot data. It is not Production Raw Data.

`ExecuteAt` is parsed as UTC and converted to `BUSINESS_TIMEZONE` before day, month, shift, end-of-day, and as-of logic.

Supported now:

- Cumulative OEE/Availability/Performance/Quality as of a day or timestamp.
- Cumulative trend from snapshots.
- Counter and snapshot metadata inspection.

Locked until approved business configuration exists:

- Period-specific Performance.
- Period-specific OEE.

If `PERFORMANCE_FORMULA_MODE=disabled`, period-specific OEE returns `PLAN_REJECTED` instead of guessing. The system must not calculate Performance from AI inference.
