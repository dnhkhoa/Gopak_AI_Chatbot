# Customer UAT Plan

Required UAT cases:

- Ask APQOEE cumulative OEE as of an explicit date.
- Ask APQOEE cumulative trend.
- Ask period-specific OEE and confirm it is rejected while Performance formula is disabled.
- Ask downtime for a single day and verify interval overlap.
- Ask loss for a single day.
- Ask APQOEE + downtime comparison.
- Ask all three source summary.
- Ask source overview, schema, and sample rows.
- Confirm no upload control or file selector is visible.
- Confirm response metadata displays source and time scope.

Release verdict must not be upgraded until live Ollama, offline runtime, fresh install, and rollback drill pass.
