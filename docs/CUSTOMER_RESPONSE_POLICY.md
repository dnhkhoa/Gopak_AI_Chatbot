# Customer Response Policy

## Scalar

Return the direct value plus file scope and whether extra filters were applied.

## Ranking / Top-N

Return the direct leading result, explain the ordering, render the table/chart, and state source/filter scope. Numeric details remain in the validated table/chart payload.

## Chart

Explain what the chart represents and confirm that it uses the same validated data as the table. Do not describe trends unless the chart is a time series.

## Clarification

Ask the smallest useful question in Vietnamese, with no technical route names.

## Error

Customer errors should be natural language and should not expose `SAFE_FAILURE`, `QueryPlan`, DuckDB exceptions, tracebacks, model names, or fallback wording.
