# Benchmark Design

Updated: 2026-06-22

## Goal

Evaluate file-scoped routing through the production `ChatApplicationService` path, not parser-only helpers.

The benchmark checks:

- Deterministic routing.
- REAL_LLM candidate routing.
- Clarification/refusal no-SQL behavior.
- Safe failure no-SQL behavior.
- File-scope isolation.
- Multipart completeness.
- Context switching.
- Cross-file switching/refusal.

## Runner

Command:

```powershell
python evaluation\run_file_scoped_benchmark.py
```

The runner:

1. Reads uploaded file metadata from `data/uploaded_files.json`.
2. Creates conversations through `ChatApplicationService`.
3. Calls `set_active_file()` for scoped cases.
4. Calls `process_message(..., debug=True)`.
5. Checks response type, SQL presence, active file metadata, and file-scope flags.
6. Writes JSON/CSV/Markdown/XLSX artifacts.

## Generated Artifacts

- `evaluation/file_scoped_benchmark_cases.json`
- `artifacts/file_scoped_benchmark_dev.json`
- `artifacts/file_scoped_benchmark_holdout.json`
- `artifacts/routing_confusion_matrix.csv`
- `artifacts/routing_metrics.json`
- `artifacts/multipart_coverage.json`
- `artifacts/context_switch_traces.json`
- `artifacts/file_switch_traces.json`
- `artifacts/file_scope_violations.json`
- `artifacts/benchmark_failures.md`
- `artifacts/benchmark_summary.md`
- `artifacts/benchmark_latency.csv`
- `artifacts/customer_benchmark_questions.xlsx`

## Latest Run

Latest run generated 320 expanded turn-cases. The expansion counts each context/cross-file sequence turn as an executable case.

Summary:

- Total: 320
- Passed: 166
- Accuracy: 51.88%
- Dev: 77/140 = 55.00%
- Holdout: 89/180 = 49.44%
- P50 latency: 233.25 ms

Category results:

| Category | Accuracy |
| --- | ---: |
| clarification | 100.00% |
| refusal | 100.00% |
| cross_file_sequence | 75.00% |
| file_scope | 60.00% |
| multipart | 51.43% |
| deterministic | 44.44% |
| context_sequence | 35.56% |
| real_llm_candidate | 26.67% |
| safe_failure | 0.00% |

## Interpretation

The file-scope safety path is in place, but the benchmark is not production-ready:

- Clarification/refusal no-SQL behavior is strong.
- Active-file isolation works for the main API path.
- Multipart decomposition is still incomplete.
- Topic restoration across A/B/A sequences is partial.
- Safe-failure benchmark cases need better policy detection for SQL-like destructive prompts.
- REAL_LLM candidate cases still need stronger qwen3.5 planning and validation.
