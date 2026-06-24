# Historical and LLM Loop Failure Audit

Generated: 2026-06-24T03:21:33.516456+00:00

## Result

- LLM invocation benchmark: 12/12 passed.
- Semantic real LLM call rate: 1.0.
- Deterministic unnecessary LLM calls: 0.
- Silent fallback count: 0.
- Fallback reason coverage: 1.0.

## Classification

No unresolved LLM loop, silent fallback, or irrelevant fallback regression remains in the post-fix run. The historical failures were classified as routing/contract regressions and are covered by `tests/test_release_regression_guards.py` plus benchmark artifacts.

## Evidence

- `artifacts/llm_invocation_final_results.json`
- `artifacts/llm_call_traces.json`
- `artifacts/llm_fallback_audit.json`
- `artifacts/llm_loop_failure_traces.json`
