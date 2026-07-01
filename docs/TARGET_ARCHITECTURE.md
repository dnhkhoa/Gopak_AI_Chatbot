# Target Architecture

The customer production app uses a fixed Production Analytics Bundle:

- `machine_downtime` = Machine Downtime
- `loss_assignment` = Loss Assignment
- `apqoee_cumulative` = APQOEE Cumulative from `Cup3.xlsx`

Customer chat no longer requires upload or file selection. The runtime flow is:

```text
User Question
-> Conversation Context Resolver
-> Intent and Metric Extraction
-> Source Capability Filter
-> Source Router
-> Structured QueryPlan or Production ExecutionPlan
-> Strict Plan Validation
-> Deterministic SQL/Python Execution
-> Result Validation
-> Evidence Pack
-> Grounded Answer / Table / Chart / Report
```

Only one physical LLM model is configured. Deterministic production analytics does not use the LLM for arithmetic, SQL, source defaults, schema guesses, joins, or fallback success answers.

EntryTransaction is deprecated and is not part of the production source registry, active manifest, active parquet cache, customer UI, or production routing.
