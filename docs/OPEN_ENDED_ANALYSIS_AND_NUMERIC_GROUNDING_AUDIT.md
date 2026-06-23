# Open-Ended Analysis And Numeric Grounding Audit

## Root Cause

- Open-ended questions such as “Dựa trên toàn bộ dữ liệu...” were routed into the generic planner/clarification path. The system did not build a source-bound `AnswerBrief`, so the composer could receive little or no grounded context and ask an irrelevant clarification.
- Multi-part table requests relied on LLM planner output too directly. When the user asked for percentage, count, or average, the final plan could drop required metrics or add unrequested metrics.
- Narrative commentary used prompt instructions only. There was no fact registry or validator to reject unsupported counts, percentages, ratios, or unit conversions.

## Fix

- Added a grounded open-ended analysis path before planner clarification. It builds a source-file-scoped `AnswerBrief` from imported parquet data and returns three concrete insights, comparison, and limitations.
- Added numeric fact registry plus `GroundedComposerValidator`. LLM commentary is accepted only when every numeric mention is present in the allowed facts and unsupported qualitative claims are absent.
- Added deterministic fallback commentary from displayed table values. If the LLM candidate fails validation, the final customer answer still remains grounded.
- Enforced question requirements after LLM planning so required count/average/percentage metrics are preserved and unrequested percentage-side metrics are removed.
- Normalized percentage display to Vietnamese label `Tỷ lệ` with `%`.

## Release Gates

- `evaluation/run_open_ended_analysis_benchmark.py`
- `evaluation/run_numeric_grounding_benchmark.py`
- `tests/test_grounding.py`

Required artifacts:

- `artifacts/open_ended_analysis_baseline.json`
- `artifacts/open_ended_analysis_final_results.json`
- `artifacts/numeric_grounding_baseline.json`
- `artifacts/numeric_grounding_final_results.json`
- `artifacts/composer_validation_failures.json`
