# Grounded Answer Composer Design

## Policy

The composer may explain only facts already present in the validated query result, conversation state, source file, filters, and table/chart payloads.

## Deterministic Composer

Used for exact scalar, schema, sample rows, provenance, data quality, and simple rankings. It adds scope, file provenance, filter notes, and table/chart guidance without creating new numeric claims.

## LLM Composer

Used for semantic follow-ups, open-ended interpretation, "đáng chú ý", "nhận xét", "kết quả nói lên điều gì", and similar requests. The LLM receives a compact JSON context from `state.last_plan` and `state.last_result_summary`, not SQL access or raw workbook access.

## Guardrails

- No SQL generation.
- No source-file changes.
- No new metrics or rankings.
- No unsupported causality or prediction.
- No internal routing/model/fallback language in customer text.
