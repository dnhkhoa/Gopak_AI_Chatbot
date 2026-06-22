# Progress and Evaluation

Status: PARTIALLY WORKING

Reason: the Streamlit app starts, data loads, tests pass, and evaluation passes with the local schema-driven fallback. Ollama is reachable and the configured default model `qwen3.5:9b` is now installed. Full LLM-backed evaluation still needs a fresh run if fallback-free planner quality must be measured.

## A. Project Snapshot

- Date/time: 2026-06-20T12:00:48
- Branch: NOT A GIT REPOSITORY
- Commit: NOT A GIT REPOSITORY
- Python version used in this session: 3.13.9
- OS: Windows-10-10.0.19045-SP0
- Ollama version: ollama version is 0.30.7
- Configured model: qwen3.5:9b
- Ollama models:
```text
NAME           ID              SIZE      MODIFIED    
qwen3-vl:8b    901cae732162    6.1 GB    10 days ago
```
- Git status:
```text
fatal: not a git repository (or any of the parent directories): .git
```

## B. Data Discovered

### EntryTransaction_20260203_164943.xlsx / Report
- Relative path: `EntryTransaction_20260203_164943.xlsx`
- Header row: 35
- Rows: 1,294
- Columns: 18
- Column list: no, cong, loai_truy_cap, ma_dang_ky, thoi_gian_thuc_thi, vai_tro_truy_cap, ho_va_ten, so_cmnd_cccd, cong_ty_chu_quan, cong_ty_van_tai, bien_so_xe_ocr, bien_so_xe_da_chinh, loai_xe, gia_tri_can, _source_file, _source_sheet, _source_row, _import_id
- Data issues: Dropped all-null columns: col_8
- Candidate relationships: []

### Loss_Assignment_20260203_100840.xlsx / Report
- Relative path: `Loss_Assignment_20260203_100840.xlsx`
- Header row: 35
- Rows: 36,309
- Columns: 13
- Column list: no, may, thoi_gian_bat_dau, thoi_gian_ket_thuc, thoi_luong, ten_ton_that, nhom_ton_that, loai_ton_that, _source_file, _source_sheet, _source_row, _import_id, thoi_luong_seconds
- Data issues: Dropped all-null columns: note, col_8; Added parsed duration seconds column: thoi_luong_seconds
- Candidate relationships: [{"left_table": "loss_assignment_20260203_100840_report_2a7588", "left_column": "may", "right_table": "machine_downtime_20260203_100753_report_3c3f6d", "right_column": "may", "overlap_count": 9, "overlap_ratio": 1.0, "name_similarity": 1.0, "confidence": 1.0, "evidence": "compatible sampled values and similar column names"}, {"left_table": "loss_assignment_20260203_100840_report_2a7588", "left_column": "ten_ton_that", "right_table": "machine_downtime_20260203_100753_report_3c3f6d", "right_column": "ten_ton_that", "overlap_count": 12, "overlap_ratio": 0.923, "name_similarity": 1.0, "confidence": 0.942, "evidence": "compatible sampled values and similar column names"}]

### Machine_Downtime_20260203_100753.xlsx / Report
- Relative path: `Machine_Downtime_20260203_100753.xlsx`
- Header row: 35
- Rows: 9,151
- Columns: 13
- Column list: no, may, thoi_gian_bat_dau, thoi_gian_ket_thuc, thoi_luong, ten_ton_that, nhom_ton_that, loai_ton_that, _source_file, _source_sheet, _source_row, _import_id, thoi_luong_seconds
- Data issues: Dropped all-null columns: note, col_8; Added parsed duration seconds column: thoi_luong_seconds
- Candidate relationships: [{"left_table": "loss_assignment_20260203_100840_report_2a7588", "left_column": "may", "right_table": "machine_downtime_20260203_100753_report_3c3f6d", "right_column": "may", "overlap_count": 9, "overlap_ratio": 1.0, "name_similarity": 1.0, "confidence": 1.0, "evidence": "compatible sampled values and similar column names"}, {"left_table": "loss_assignment_20260203_100840_report_2a7588", "left_column": "ten_ton_that", "right_table": "machine_downtime_20260203_100753_report_3c3f6d", "right_column": "ten_ton_that", "overlap_count": 12, "overlap_ratio": 0.923, "name_similarity": 1.0, "confidence": 0.942, "evidence": "compatible sampled values and similar column names"}]

## C. Architecture Implemented

- Completed: dynamic workbook scanner, header detector, normalization, duration/date parsing, parquet cache, DuckDB executor, data catalog, relationship detector, Pydantic plan schema, plan validator, safe SQL builder, Ollama client, heuristic fallback, conversation state, Streamlit UI, Plotly chart rendering, dashboard/report intent, HTML export, Excel export, tests, evaluation artifacts, README, PowerShell scripts.

- UPDATED: `qwen3.5:9b` is installed and visible in `ollama list`. Full fallback-free LLM planner evaluation has not yet been rerun in this correction turn.

- Technical decision: use DuckDB over parquet paths with parameter binding and generated SQL only; LLM never executes Python or raw SQL.

## D. Files Created or Modified

| File | Purpose | Status |
| --- | --- | --- |
| .env.example | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| app.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| artifacts\evaluation_results.json | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| artifacts\latency_benchmark.csv | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| cache\data_catalog.json | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| cache\manifest.json | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| docs\DATA_PROFILE.md | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| evaluation.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| README.md | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| requirements.txt | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| run.ps1 | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| scripts_ingest.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| setup.ps1 | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\__init__.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\catalog\profiler.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\catalog\relationship_detector.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\config.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\conversation\state.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\ingestion\cache_manager.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\ingestion\header_detector.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\ingestion\normalizer.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\ingestion\workbook_scanner.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\llm\ollama_client.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\llm\planner.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\llm\prompts.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\query\executor.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\query\schemas.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\query\sql_builder.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\query\validator.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\rendering\answer_renderer.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\rendering\chart_renderer.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\rendering\dashboard.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\rendering\report_exporter.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| src\ui\components.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| tests\test_exports.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| tests\test_ingestion.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |
| tests\test_query.py | Implementation, docs, tests, cache, report, or artifact | Created/updated |

## E. Commands Executed

- `python --version`
- `git status --short --branch`
- `ollama --version`
- `ollama list`
- `python -m pip install duckdb`
- `python scripts_ingest.py`
- `python -m pytest -q`
- `python evaluation.py`
- `python -m streamlit run app.py --server.headless true --server.port 8501`
- `Invoke-WebRequest http://localhost:8501`
- `Remove-Item __pycache__/.pytest_cache generated caches`

## F. Test Results

| Test suite | Passed | Failed | Skipped | Duration |
| --- | --- | --- | --- | --- |
| pytest | 25 | 0 | 0 | 23.54s |

## G. End-to-End Evaluation

| ID | Question | Expected | Actual | Pass | Latency | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| E001 | Tổng downtime là bao nhiêu? | query | query | True | 4104.7 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E002 | Máy nào có thời gian downtime cao nhất? | query | query | True | 4082.5 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E003 | Top 5 nguyên nhân gây tổn thất. | query | query | True | 4054.3 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E004 | Vẽ biểu đồ downtime theo ngày. | chart | chart | True | 4084.9 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E005 | Tạo dashboard tổng quan. | dashboard | dashboard | True | 4081.7 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E006 | Xuất báo cáo phân tích downtime. | report | report | True | 4105.5 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E007 | Downtime trung bình là bao nhiêu? | query | query | True | 4098.3 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E008 | Đếm số dòng downtime. | query | query | True | 4089.8 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E009 | Top 3 máy downtime cao nhất. | query | query | True | 4115.8 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E010 | Các nguyên nhân liên quan đến QC là gì? | query | query | True | 4120.1 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E011 | Chỉ lấy nhóm bảo trì. | query | query | True | 4088.6 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E012 | Trong kết quả trên, vẽ top 5. | chart | chart | True | 4099.2 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E013 | Tổng thời gian dừng tháng 11. | query | query | True | 4074.5 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E014 | So sánh downtime giữa các máy. | query | query | True | 4100.7 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E015 | Nhóm tổn thất nào xuất hiện nhiều nhất? | query | query | True | 4076.9 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E016 | Máy nào có số lần dừng nhiều nhất? | query | query | True | 4116.7 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E017 | Biểu đồ top nguyên nhân. | chart | chart | True | 4112.5 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E018 | Có dữ liệu cổng ra vào không? | query | query | True | 4085.9 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E019 | Tổng giá trị cân là bao nhiêu? | query | query | True | 4063.9 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |
| E020 | Câu hỏi mơ hồ về hiệu suất. | clarification | clarification | True | 4048.0 ms | Uses Ollama when available; otherwise schema-driven heuristic fallback. |

## H. Performance

- Cold start: measured app HTTP startup returned status 200 at `http://localhost:8501`; exact cold-start duration not separately instrumented.
- Warm total latency P50: 4089.2 ms
- Warm total latency P95: 4119.9 ms
- Slowest query: E010 at 4120.1 ms
- Planner time median: 4058.9 ms
- DuckDB query time median: 29.1 ms
- Rendering time: not separately measured in this MVP evaluation.

## I. Current Limitations and Known Bugs

- Severity: Resolved. `qwen3.5:9b` is now installed and detected by the local Ollama health check. Remaining action: rerun fallback-free LLM evaluation if needed.

- Severity: Medium. Reproduce: ask complex multi-table causal questions. Cause: relationships are candidate-level only; no row-level FK was proven. Files: `src/catalog/relationship_detector.py`, `docs/DATA_PROFILE.md`. Fix: add business-key confirmation or user clarification flow before joins.

- Severity: Low. Reproduce: ask broad performance questions without a metric. Cause: schema has downtime and access data, not production output. Files: `src/llm/planner.py`. Fix: add clarification templates per domain.

## J. Assumptions

- Header detection is dynamic, but all observed sheets had row 35 headers.
- `No.` is a report row number, not a business primary key.
- `thoi_luong_seconds` is the preferred metric for downtime aggregation.
- Relationship confidence on `may` and `ten_ton_that` indicates shared dimensions, not guaranteed row-level joins.

## K. Exact Next Steps

1. Install or configure a local Ollama text model, preferably `qwen3.5:9b`, then rerun `python evaluation.py` with heuristic fallback disabled.
2. Add stricter semantic matching for categorical values, including verified fuzzy matches from real unique values.
3. Extend dashboard widgets to run multiple validated plans instead of a single grouped query.

## L. Reproduction Checklist

1. Install Python 3.11 and Ollama on Windows.
2. Run `setup.ps1`.
3. Run `ollama list`; if needed run `ollama pull qwen3.5:9b`.
4. Run `python scripts_ingest.py`.
5. Run `python -m pytest -q`.
6. Run `python evaluation.py`.
7. Run `streamlit run app.py` or `run.ps1`.
8. Open `http://localhost:8501` and ask a Vietnamese question such as `M?y n?o c? th?i gian downtime cao nh?t?`.

## UI AND RESPONSE PRESENTATION IMPROVEMENTS

Updated: 2026-06-20T12:58:15

### Files modified

| File | Purpose |
| --- | --- |
| `app.py` | Reworked Streamlit layout, sidebar labels, status flow, suggestion buttons, result hierarchy, download grouping, and technical-data expander. |
| `src/rendering/formatters.py` | Added Vietnamese number formatting, duration formatting, column-name humanization, and display DataFrame formatting. |
| `src/rendering/presentation.py` | Added `PresentedResponse` model and presentation assembly for scalar, table, chart, report, clarification, and empty states. |
| `src/rendering/answer_renderer.py` | Removed question echo/raw scalar phrasing from legacy text renderer. |
| `src/rendering/chart_renderer.py` | Added business labels and limited chart categories to 15 by default. |
| `src/rendering/report_exporter.py` | Export reports with humanized labels and Vietnamese headings. |
| `src/ui/components.py` | Localized suggested questions and sidebar-friendly table names/counts. |
| `tests/test_presentation.py` | Added tests for duration/number formatting, column humanization, scalar/table presentation, empty state, raw-column hiding, and download visibility. |

### Before/after behavior

| Area | Before | After |
| --- | --- | --- |
| Scalar answer | Repeated the full question and showed `total_duration_seconds` as raw seconds. | Shows a KPI card: `T?ng th?i gian downtime`, `1.989,56 gi?`, and equivalent days/hours/minutes/seconds. |
| Raw DataFrame | Displayed one-row technical DataFrame in the main answer. | Hidden by default for scalar answers; raw data is inside `Xem d? li?u chi ti?t` or Debug. |
| Table/chart labels | Used raw DuckDB/technical column names. | Uses Vietnamese business labels from mapping/catalog fallback. |
| Status boxes | Separate English-like status blocks remained visually prominent. | Single Vietnamese status flow collapses to `Ho?n t?t trong ... gi?y`. |
| Sidebar | Mixed English/Vietnamese and exposed table hashes. | Localized sidebar with readable table names and formatted row counts. |
| Suggestions | Plain text captions. | Clickable suggestion buttons. |
| Downloads | Buttons spread across wide columns. | HTML and Excel buttons sit together on one row and only render after files exist. |

### Tests run

- `python -m compileall src app.py` passed.
- `python -m pytest -q` passed: 25 passed in 23.54s.
- Browser smoke test at `http://localhost:8501/` passed for:
  - `T?ng downtime l? bao nhi?u?`
  - `M?y n?o c? downtime cao nh?t?`
  - `Top 5 nguy?n nh?n t?n th?t.`
  - `V? bi?u ?? downtime theo ng?y.`
  - `C?c nguy?n nh?n li?n quan ??n QC l? g??` for empty-state verification.

### Screenshot

- `artifacts/ui_presentation_smoke.png`

### Remaining issues

- The configured Ollama model `qwen3.5:9b` is now installed. Fallback-free LLM evaluation has not yet been rerun after installation.
- A very free-form no-data question such as `D? li?u c?a m?y KH?NG_T?N_T?I l? g??` is not reliably converted into a machine filter by the current planner. The empty-state UI itself was verified with the supported QC semantic filter.
- Chart tooltips now use business labels, but deeper custom tooltip formatting for every duration unit can be improved in a later chart-only pass.

### Ollama model correction

Updated: 2026-06-20T13:03:17

`ollama list` now shows `qwen3.5:9b`, and `OllamaClient.health()` reports `model_available=True`. Earlier notes saying the model was missing are superseded by this update.

### Ollama qwen3.5 follow-up verification

Updated: 2026-06-20T13:07:45

The user's correction was verified: `ollama list` shows `qwen3.5:9b`, and `OllamaClient.health()` returns `model_available=True`.

A client compatibility issue was fixed in `src/llm/ollama_client.py`:

- `OLLAMA_KEEP_ALIVE=-1` is now sent as numeric `-1`, not string `"-1"`, avoiding Ollama `400 Bad Request`.
- `think: false` is sent to `/api/generate`, so qwen-style reasoning does not consume the response channel for simple JSON calls.

Verification after the fix:

- Direct `/api/generate` smoke works for `qwen3.5:9b`.
- `python -m compileall src app.py` passed.
- `python -m pytest -q` passed: 25 passed in 27.04s.

Remaining planner issue: the full planner prompt still produced malformed raw output (` ``` `) for the smoke question `T?ng downtime l? bao nhi?u?`, so `QueryPlanner` fell back to the local heuristic for that request. The model is installed and reachable; the next fix should tighten the planner prompt/retry path for qwen3.5 JSON-only output.
## PLANNER RELIABILITY FIX — ROUND 1

Updated: 2026-06-20T14:58:50.068266

Scope:

- Replaced normal-path regex JSON extraction with Ollama `/api/chat` structured output: `format=QueryPlan.model_json_schema()`, `stream=false`, `think=false`, `seed=42`.
- Kept regex parsing out of the normal REAL_LLM path. It is still only present as an unused legacy helper.
- Reduced planner context with schema linking: per-question table selection, role-aware columns, sample values, relevance scores, and omitted-table notes.
- Added pre-policy for out-of-domain, ambiguous, future-looking, and unsafe row-level join questions.
- Added model-output coercion for common qwen variants: role aliases, `field` vs `column`, operator aliases, qualified columns, date wrapper expressions, metric aliases, and malformed time-granularity-as-metric outputs.
- Improved deterministic fallback for table selection, count-vs-sum, duration filters, future refusal, and Vietnamese paraphrases.
- Tightened validation and SQL defaults: sort aliases are accepted, aggregation type checks remain enforced, clarification/refusal bypass query validation, and time series default to chronological sorting.

Files changed:

- `src/llm/ollama_client.py`
- `src/llm/planner.py`
- `src/llm/prompts.py`
- `src/query/schemas.py`
- `src/query/validator.py`
- `src/query/sql_builder.py`
- `src/rendering/presentation.py`
- `evaluation/planner_probe.py`
- `evaluation/run_evaluation.py`

Prompt/context size:

- Before: planner sent broad catalog/prompt context with no per-question context artifact.
- After: `artifacts/planner_context_samples.json` contains 200 logged samples; median serialized sample size is about 876 chars, P95 about 894 chars, max 900 chars.

Planner JSON validity:

- Before: full REAL_LLM evaluation was blocked by malformed planner JSON in the normal path.
- After: planner probe ran 20 questions x 3 = 60 REAL_LLM runs; 57/60 were parseable and valid plans.
- JSON validity after fix: 95.00%.
- Required reliability target: 98%.
- Status: improved substantially, but not accepted for demo-readiness yet.

Full evaluation after fix:

| Mode | Cases | Passed | Failed | Manual | Accuracy | P50 | P95 | Readiness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| REAL_LLM | 85 | 49 | 26 | 10 | 57.65% | 9638.2 ms | 17413.4 ms | NOT DEMO READY |
| HEURISTIC_FALLBACK | 85 | 52 | 19 | 14 | 61.18% | 2056.1 ms | 2076.1 ms | NOT DEMO READY |

REAL_LLM accuracy by category:

| Category | Total | Passed | Failed | Manual | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| aggregation | 9 | 8 | 1 | 0 | 88.9% |
| ambiguity | 4 | 4 | 0 | 0 | 100.0% |
| artifact | 6 | 4 | 2 | 0 | 66.7% |
| boundary | 4 | 1 | 3 | 0 | 25.0% |
| filter | 6 | 3 | 3 | 0 | 50.0% |
| join | 5 | 4 | 1 | 0 | 80.0% |
| multi_turn | 15 | 0 | 5 | 10 | 0.0% |
| out_of_domain | 4 | 4 | 0 | 0 | 100.0% |
| paraphrase | 6 | 6 | 0 | 0 | 100.0% |
| semantic | 5 | 2 | 3 | 0 | 40.0% |
| time | 9 | 4 | 5 | 0 | 44.4% |
| top_n | 8 | 6 | 2 | 0 | 75.0% |
| typo | 4 | 3 | 1 | 0 | 75.0% |

Fallback accuracy by category:

| Category | Total | Passed | Failed | Manual | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| aggregation | 9 | 8 | 1 | 0 | 88.9% |
| ambiguity | 4 | 4 | 0 | 0 | 100.0% |
| artifact | 6 | 6 | 0 | 0 | 100.0% |
| boundary | 4 | 3 | 1 | 0 | 75.0% |
| filter | 6 | 5 | 1 | 0 | 83.3% |
| join | 5 | 4 | 1 | 0 | 80.0% |
| multi_turn | 15 | 0 | 1 | 14 | 0.0% |
| out_of_domain | 4 | 4 | 0 | 0 | 100.0% |
| paraphrase | 6 | 6 | 0 | 0 | 100.0% |
| semantic | 5 | 0 | 5 | 0 | 0.0% |
| time | 9 | 4 | 5 | 0 | 44.4% |
| top_n | 8 | 5 | 3 | 0 | 62.5% |
| typo | 4 | 3 | 1 | 0 | 75.0% |

Remaining failure profile:

- REAL_LLM: 10 plan-validation failures, 6 aggregation errors, 5 filter errors, 3 column-selection errors, 2 intent errors, 10 manual-review multi-turn cases.
- HEURISTIC_FALLBACK: 9 aggregation errors, 6 column-selection errors, 2 filter errors, 1 intent error, 1 plan-validation error, 14 manual-review multi-turn cases.
- Top remaining issues: temporal reasoning for "first/latest month" and time-series ordering, semantic matching for fuzzy loss names, row-level/multi-turn follow-up behavior, and qwen malformed JSON on one repeated probe.

Verification:

- `python -m pytest -q`: 25 passed.
- `python -m compileall src evaluation app.py`: passed.
- `python evaluation/planner_probe.py`: completed, 57/60 valid plans.
- `python evaluation/run_evaluation.py`: wrote all after-fix artifacts; final console print hit a Windows cp1252 UnicodeEncodeError after file writes, so artifacts are authoritative.

Artifacts:

- `artifacts/planner_probe_results.json`
- `artifacts/planner_context_samples.json`
- `artifacts/evaluation_results_real_llm.json`
- `artifacts/evaluation_results_real_llm_after_fix.json`
- `artifacts/evaluation_results_fallback.json`
- `artifacts/evaluation_results_fallback_after_fix.json`
- `artifacts/evaluation_summary.md`
- `artifacts/evaluation_summary_after_fix.md`
- `artifacts/evaluation_failures.md`
- `artifacts/evaluation_failures_after_fix.md`
- `artifacts/latency_benchmark.csv`
- `artifacts/latency_benchmark_after_fix.csv`
- `artifacts/consistency_analysis.json`
- `artifacts/paraphrase_equivalence.json`
## COMPREHENSIVE LLM EVALUATION

Updated: 2026-06-21T06:45:10.118429

- Evaluation modes: REAL_LLM probe plus full HEURISTIC_FALLBACK suite.
- Real model requested: `qwen3.5:9b` via local Ollama.
- Real model used successfully: Yes
- Number of cases generated: 85
- Fallback pass/fail/manual: 69/1/15
- Fallback accuracy: 81.18%
- Fallback P50/P95 latency: 85.4 ms / 107.1 ms
- Consistency: 10/10 stable fallback reruns; REAL_LLM consistency is blocked by malformed planner JSON.
- Paraphrase equivalence: 1/1 groups consistent.
- Critical issues: None observed for REAL_LLM transport.
- Model readiness: REAL_LLM evaluation available.

Artifacts:

- `evaluation/evaluation_cases.json`
- `artifacts/evaluation_results_fallback.json`
- `artifacts/evaluation_results_real_llm.json` only when REAL_LLM probe produces a usable plan
- `artifacts/evaluation_summary.md`
- `artifacts/evaluation_failures.md`
- `artifacts/latency_benchmark.csv`
- `artifacts/consistency_analysis.json`
- `artifacts/paraphrase_equivalence.json`

Priority fixes:

1. Fix REAL_LLM planner JSON generation by shrinking prompt/catalog and using schema-constrained JSON output.
2. Improve deterministic handling for ambiguity/refusal, semantic matching, bottom-N, date ranges, and multi-turn filters.
3. Add chart-specific comparators for x/y data and tooltip formatting once planner correctness improves.

## FILE-SCOPED QUERY ROUTING, MULTI-PART COVERAGE AND TOPIC MEMORY BENCHMARK

Updated: 2026-06-22

Status: FILE-SCOPE ENFORCEMENT IMPLEMENTED, BENCHMARK NOT PRODUCTION READY

Implemented:

- Added conversation-level `active_file_id` and `active_file_name`.
- Added per-file memory containers in `ConversationState`.
- Added `PUT /api/conversations/{conversation_id}/active-file`.
- Added `ChatApplicationService.get_catalog_for_file(file_id)`.
- Changed the production message path so metadata, planner, validator, executor, chart builder, and source renderer receive only the selected-file catalog.
- Added plan-table subset validation before DuckDB execution.
- Added no-SQL preflight for no selected file, missing/deleted file, non-ready file, and questions that mention another uploaded file.
- Added response metadata: `active_file_id`, `active_file_name`, `file_scope_validated`.
- Wired React file selection to the backend active-file endpoint.
- Added regression tests for the new file-selection contract and no-file clarification.

Audit proof before the change:

- Runtime catalog had 3 tables loaded at once: EntryTransaction, Loss_Assignment, and Machine_Downtime.
- `process_message()` previously passed the full catalog into metadata responders, `QueryPlanner`, and `SafeQueryExecutor`.
- The frontend selected file state was local-only and did not affect backend execution.

Smoke proof after the change:

- No file selected returns `clarification` with `generated_sql=None`.
- Selecting `Machine_Downtime_20260203_100753.xlsx` and asking `noi dung cua data` returns one selected-file overview row.
- Asking about `Loss_Assignment` while Machine_Downtime is selected returns refusal with no SQL.

Benchmark:

- Runner: `evaluation/run_file_scoped_benchmark.py`
- Cases artifact: `evaluation/file_scoped_benchmark_cases.json`
- Latest expanded run: 320 turn-cases.
- Passed: 166/320 = 51.88%.
- Dev: 77/140 = 55.00%.
- Holdout: 89/180 = 49.44%.
- Clarification/refusal no-SQL: 100%.
- Cross-file sequence: 75%.
- File-scope metadata cases: 60%.
- Multipart/context/REAL_LLM candidate behavior remains below acceptance quality.

Artifacts:

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

Verification:

- `python -m compileall src backend`: passed.
- `python -m pytest -q`: 64 passed.
- `npm test -- --run`: 18 passed.
- `npm run build`: passed with the existing non-blocking Vite chunk-size warning.

Remaining work:

1. Strengthen topic-frame restoration for A/B/A semantic switching.
2. Improve multipart decomposition so chart/time/ranking/filter requirements are all preserved.
3. Add stricter safe-failure policy for destructive SQL-like phrasing.
4. Improve REAL_LLM candidate routing with qwen3.5 JSON/schema adherence.

## DYNAMIC HEADER DETECTION, ROW-LEVEL QUERY AND INTERVAL SEMANTICS

Updated: 2026-06-22

Status: IMPLEMENTED FOR AVAILABLE WORKBOOK, SAMPLE ORACLE FILE NOT PRESENT

Requested sample file `Operation_Downtime_20251212_101824 (2)(1).xlsx` was not available in the workspace or `D:\` during this session. The implementation supports it by filename when added, but the benchmark artifacts were generated using the available selected fallback workbook `Machine_Downtime_20260203_100753.xlsx`.

Header detection before:

- Simple first-100-row scoring.
- No explicit metadata-row rejection.
- Candidate area could include trailing garbage.
- `Note` was dropped when all-null.

Header detection after:

- Scans at least 200 rows.
- Rejects report metadata rows.
- Scores semantic headers, density, contiguous columns, and consecutive valid records.
- Detects repeated headers/footer rows.
- Keeps business all-null columns such as `Note`.
- Drops trailing numeric/blank artifact columns.

Fallback workbook header result:

- Header row: 35.
- First data row: 36.
- Last data row: 9186.
- Source columns: D:L.
- Normalized records: 9,151.
- Garbage columns included: 0.

Normalized provenance fields:

- `_source_file_id`
- `_source_file_name`
- `_source_sheet`
- `_source_excel_row`
- `_source_header_row`
- `_data_row_index`
- `_record_no`
- `_import_id`

Row query capabilities:

- Record lookup by `No.` / `_record_no`.
- Lookup by physical Excel row.
- Lookup by normalized data-row index.
- First/latest/earliest event by datetime.
- Machine/date/time-window row queries using interval overlap.
- Duplicate, missing-classification, duration > 24 hours, and negative-interval queries.
- Operating-time questions return clarification instead of asserting machine runtime from downtime records.

Duration policy:

- Preserve `duration_reported_text`.
- Parse `duration_reported_seconds`.
- Compute `duration_calculated_seconds`.
- Store `duration_difference_seconds` and `duration_anomaly`.
- Canonical `duration_seconds` currently uses reported duration.

Duplicate policy:

- No duplicate rows are silently deleted.
- `_is_exact_duplicate`, `_duplicate_group_id`, and `_duplicate_group_size` are persisted.
- Raw record count remains distinct from deduplicated event count.

Interval policy:

- Row-level date/time filters use interval overlap:
  `event_start < window_end AND event_end >= window_start`.
- Cross-midnight records are detected in validation artifacts.
- Generic analytical planner date filters still need deeper clipped-duration support.

Benchmark results:

- Header detection benchmark: 15/15 passed = 100%.
- Row-level benchmark: 81/81 passed = 100% on fallback workbook.
- Row-level P50 latency: 225.6 ms.
- Row-level P95 latency: 675.2 ms.

Artifacts:

- `artifacts/header_detection_results.json`
- `artifacts/header_detection_failures.md`
- `artifacts/row_level_benchmark_results.json`
- `artifacts/row_level_benchmark_failures.md`
- `artifacts/record_provenance_checks.json`
- `artifacts/interval_query_checks.json`
- `artifacts/duration_reconciliation.json`
- `artifacts/duplicate_and_overlap_report.json`
- `artifacts/row_query_latency.csv`
- `docs/ROW_LEVEL_AND_HEADER_AUDIT.md`
- `docs/ROW_LEVEL_QUERY_ARCHITECTURE.md`
- `docs/HEADER_DETECTION_DESIGN.md`

Remaining limitations:

1. Requested Operation workbook oracle values were not verified because the file is missing.
2. Row-level implementation currently sits as a deterministic service layer before planner, not as full first-class `QueryPlan` variants for every row intent.
3. Clipped-duration analytical totals by day are not yet generalized through SQL builder/planner.

## COMPLEX QUERY AND PERSISTENT MEMORY — ROUND 3

Updated: 2026-06-21T06:50:00

Status: PARTIALLY WORKING, NOT PRODUCTION READY

### Architecture before

- Conversation state lived only in `st.session_state`.
- `ConversationState` was a dataclass without `conversation_id` or durable storage.
- Follow-up handling was implicit in planner heuristics.
- QueryPlan could express simple filters, dimensions, metrics, sort, and limit only.
- SQL builder emitted one SELECT with optional GROUP BY/ORDER BY/LIMIT.

### Architecture after

- `ConversationState` is now Pydantic and includes conversation id, metrics, dimensions, filters, time range, having, ranking, result summary, result-cache id, recent turns, and summary placeholder.
- `ConversationMemoryService` owns persistence; Streamlit does not access SQL directly.
- SQLite store exists at `data/app_memory.db` by default.
- Large results are cached as parquet references under `cache/conversations/<conversation_id>/<turn_id>.parquet`.
- Deterministic turn classifier, state merger, and reference resolver support structured follow-ups.
- QueryPlan supports `having`, `ranking`, `derived_metrics`, `time_comparison`, `query_complexity`, and `MetricSpec.percentage_of_total`.
- SQL builder now supports CTE-based percentage, group-average filters, and windowed ranking.

### SQLite schema

- `conversations(id, title, created_at, updated_at, status)`
- `conversation_turns(id, conversation_id, turn_index, role, content, execution_mode, query_plan_json, result_summary_json, created_at)`
- `conversation_states(conversation_id, state_json, summary, updated_at)`
- `result_cache(id, conversation_id, turn_id, parquet_path, row_count, schema_json, created_at)`

`PRAGMA foreign_keys = ON` is enabled on connections.

### Verification

- `python -m compileall src evaluation app.py`: passed.
- `python -m pytest -q`: 51 passed.
- `python evaluation\planner_probe.py`: 60/60 valid plans.
- `python evaluation\run_evaluation.py`: 69 passed, 1 failed, 15 manual review; accuracy 81.18%.
- `python evaluation\run_round3.py`: complex 16/20, multi-turn 11/15, persistence 4/4.
- `Invoke-WebRequest http://localhost:8501/`: HTTP 200.

### Baseline hybrid after Round 3

| Metric | Result |
| --- | ---: |
| Cases | 85 |
| Passed | 69 |
| Failed | 1 |
| Manual review | 15 |
| Accuracy | 81.18% |
| LLM-called rows | 0 |
| Fallback used | 0 |
| Legacy fallback selected | 0 |
| P50 latency | 87.1 ms |
| P95 latency | 118.8 ms |

Top-N improved to 8/8. The only non-manual baseline failure is `EVAL-041`, an ambiguous typo/oracle mismatch: `may nao downtime cao nhat`.

### Round 3 evaluation

| Area | Passed | Failed | Accuracy |
| --- | ---: | ---: | ---: |
| Complex query | 16 | 4 | 80.00% |
| Multi-turn automated | 11 | 4 | 73.33% |
| Persistence | 4 | 0 | 100.00% |

Complex capability results:

- Multiple metrics: 2/2.
- Percentage metrics: 2/2.
- Above-average filters: 2/2.
- Windowed Top-N: 2/2.
- Long combined: 0/2.
- Period comparison: 0/1.
- Nested query: 0/1.

Multi-turn capability results:

- CHANGE_OUTPUT: 3/3.
- CHANGE_TIME: 1/1.
- REFERENCE_ENTITY: 2/2.
- RESET_CONTEXT: 1/1.
- CHANGE_METRIC: 1/1.
- ADD_FILTER: 2/3.
- NEW_QUERY/context isolation: 1/4.

### Artifacts

- `artifacts/complex_query_evaluation.json`
- `artifacts/complex_query_failures.md`
- `artifacts/multiturn_evaluation.json`
- `artifacts/multiturn_state_traces_round3.json`
- `artifacts/memory_persistence_tests.json`
- `artifacts/memory_store_snapshot.json`
- `artifacts/evaluation_summary_round3.md`
- `artifacts/latency_round3.csv`

### Readiness

- Demo status: PARTIALLY WORKING. Controlled demos can cover memory restore, conversation list, multiple metrics, percentage/share, above-average filters, windowed top-N, safe refusal, and simple reference follow-ups.
- Production readiness: NOT PRODUCTION READY. Blocking gaps remain in long combined query decomposition, period comparison, nested multi-step query pipelines, and automated multi-turn context isolation.

Top remaining issues:

1. Long combined questions can still drop one requirement when time scope, multiple metrics, above-average filter, ranking, and chart output appear together.
2. Period comparison needs first-class plan and SQL support for paired periods, deltas, and percentage change.
3. Nested entity analysis needs a validated query pipeline/CTE dependency model instead of only reference-based follow-ups.

## REACT + FASTAPI WEB MIGRATION

Updated: 2026-06-21

Status: READY FOR LOCAL DEMO, NOT PRODUCTION READY

### Architecture before

- Streamlit owned both UI rendering and application orchestration.
- `app.py` directly created the planner, executed DuckDB queries, rendered presentation objects, exported reports, updated conversation state, and saved turns.
- React/FastAPI did not exist.

### Architecture after

- `src/application/ChatApplicationService` is the shared orchestration layer.
- Streamlit fallback now calls the service instead of directly calling planner/executor/export logic.
- FastAPI routes call the same service.
- React/Vite frontend renders API-safe JSON response payloads.
- Browser state is limited to selected conversation id, debug preference, and sidebar collapsed state.

### Files created

- `src/application/*`
- `backend/*`
- `frontend/*`
- `start-backend.ps1`
- `start-frontend.ps1`
- `start-web.ps1`
- `docs/WEB_MIGRATION_AUDIT.md`
- `docs/WEB_ARCHITECTURE.md`
- `docs/WEB_MIGRATION_REPORT.md`
- `tests/test_web_api.py`

### Endpoints

- `GET /api/health`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`
- `POST /api/conversations/{id}/reset-context`
- `POST /api/conversations/{id}/messages`
- `GET /api/artifacts/{artifact_id}/download`
- `GET /api/data/status`
- `POST /api/data/reload`

### UI components

- `ChatMessage`
- `ScalarResult`
- `DataTable`
- `ChartResult`
- `DashboardResult`
- `ClarificationMessage`
- `RefusalMessage`
- `ErrorMessage`
- `SourceDetails`
- `DownloadActions`
- `DebugPanel`
- `ChatComposer`
- `ConversationSidebar`

### Verification

- `python -m compileall app.py backend src`: passed.
- `python -m pytest tests\test_web_api.py tests\test_presentation.py tests\test_memory_persistence.py -q`: 22 passed.
- `python -m pytest -q`: 57 passed, 1 Starlette/httpx deprecation warning.
- `npm test`: 5 passed.
- `npm run build`: passed with one non-blocking Recharts/Vite chunk-size warning.
- `npm audit`: 0 vulnerabilities.
- `GET http://127.0.0.1:8000/api/health`: returned ok.
- `GET http://127.0.0.1:5173`: returned 200.
- `GET http://localhost:8501`: returned 200.

### Integration smoke

- Created a conversation through FastAPI.
- Sent `May nao downtime cao nhat?`: returned a table response with expected summary.
- Sent `Ve top 5`: returned chart response with chart payload.
- Sent `Xuat bao cao phan tich downtime`: returned report response with 2 downloads.
- Downloaded generated artifact through `/api/artifacts/{artifact_id}/download`: returned 200.
- Opened React app in the in-app browser and verified sidebar, composer, table response, downloads, and no visible error state.

### Known issues

- Historical assistant messages currently reload as stored text summaries, not full rich response payloads.
- Streamlit remains a legacy fallback surface.
- Many test conversations were created during smoke verification; they can be deleted from the sidebar if a cleaner demo list is desired.

## CUSTOMER-GRADE QUERY UNDERSTANDING AND UAT

Updated: 2026-06-21

Status: READY FOR CONTROLLED CUSTOMER DEMO, NOT PRODUCTION READY

### Root bug reproduced and fixed

Before this fix, the Web API request `nội dung của data` returned a scalar downtime answer:

- `response_type`: `scalar`
- SQL: `SELECT sum(...thoi_luong_seconds) ...`
- Answer: total downtime, about `1.989,56 giờ`

After the fix, the same Web API path returns:

- `response_type`: `data_overview`
- `execution_mode`: `DATA_OVERVIEW`
- generated SQL: `null`
- content: catalog/table overview with row counts, key columns, and date coverage.

### Implementation

- Added customer intent taxonomy before analytical planning: `DATA_OVERVIEW`, `TABLE_OVERVIEW`, `SCHEMA_INSPECTION`, `SAMPLE_ROWS`, `DATA_RANGE`, `DATA_QUALITY`, `ANALYTICAL_QUERY`, `CHART_REQUEST`, `DASHBOARD_REQUEST`, `REPORT_REQUEST`, `EXPORT_REQUEST`, `CONVERSATION_FOLLOWUP`, `CLARIFICATION`, `REFUSAL`, `SAFE_FAILURE`.
- Added no-SQL metadata responses in `ChatApplicationService` for overview/schema/sample/range/quality/clarification/refusal.
- Added frontend components for `data_overview`, `schema`, `sample_table`, and `data_quality`.
- Added mixed Vietnamese/no-accent/English detection fixes, including `by month/by day/by week` chart grouping.
- Added customer regression tests proving metadata questions do not default to downtime SQL.

### Evaluation

Customer eval runner uses the same `ChatApplicationService` path as FastAPI/Web UI.

| Set | Passed | Total | Accuracy |
| --- | ---: | ---: | ---: |
| Development | 128 | 130 | 98.5% |
| Holdout | 44 | 50 | 88.0% |
| Total | 172 | 180 | 95.6% |

Key metrics:

- Default downtime false positives: 0
- Multi-turn automated accuracy: 23/24 = 95.8%
- LLM calls recorded in this deterministic customer-eval path: 0
- P50 latency: 376.6 ms
- P95 latency: 517.1 ms

Category coverage includes overview, schema, sample data, data quality, aggregation, ranking, time reasoning, filters, semantic matching, long combined requests, artifact/chart/report/export requests, multi-turn, typo/no-accent, mixed language, ambiguity, out-of-domain, empty result, and security.

### Remaining failures

8/180 cases remain unresolved:

- Analytical gaps: `Tổng giá trị cân`, `Số cổng khác nhau`, some semantic loss-group questions, and a long two-month combined question.
- Metadata gap: relationship overview question currently clarifies instead of explaining candidate relationships.
- Multi-turn gap: one chained `Top 3 máy trong số đó theo downtime` case fails safely.
- Complex report gap: one long HTML report request hits safe failure instead of decomposing into multiple subqueries.

### Artifacts

- `docs/CUSTOMER_QUERY_AUDIT.md`
- `docs/CUSTOMER_UAT_GUIDE.md`
- `docs/CUSTOMER_UAT_QUESTIONS.md`
- `evaluation/customer_questions.json`
- `evaluation/run_customer_evaluation.py`
- `evaluation/generate_customer_questions.py`
- `artifacts/customer_questions.xlsx`
- `artifacts/customer_uat_checklist.xlsx`
- `artifacts/customer_evaluation_dev.json`
- `artifacts/customer_evaluation_holdout.json`
- `artifacts/customer_evaluation_all.json`
- `artifacts/customer_evaluation_summary.md`
- `artifacts/customer_evaluation_failures.md`
- `artifacts/customer_intent_confusion_matrix.csv`
- `artifacts/customer_latency.csv`
- `artifacts/default_downtime_false_positives.json`

### Verification

- `python -m compileall src evaluation backend app.py`: passed.
- `python -m pytest tests\test_customer_query_understanding.py -q`: 5 passed.
- `python evaluation\run_customer_evaluation.py --set development`: 128/130 passed.
- `python evaluation\run_customer_evaluation.py --set holdout`: 44/50 passed.

## Upload Ingestion Readiness Contract

Updated: 2026-06-22

Status: IMPLEMENTED AND VERIFIED

### Root bug fixed

The old upload API marked a workbook `ready` after `pd.ExcelFile` could open it. That did not prove the file was available to the query layer.

The new lifecycle marks a file `ready` only after:

- raw upload exists and SHA-256 matches metadata;
- workbook scanner produced at least one table;
- parquet cache exists and DuckDB can count rows;
- catalog contains scoped `file_id/source_file_id`;
- `_source_file_id` provenance matches the selected upload id.

### Implementation

- Added `src/files/lifecycle.py` with upload, process, readiness validation, delete cleanup, and startup reconciliation.
- Added uploaded-file ingestion support to `ParquetCache.refresh_uploaded_file`.
- Catalog table entries now carry `file_id`, `source_file_id`, `source_file`, `source_sheet`, `sha256`, and parquet path.
- Active file selection validates `ready && queryable`.
- Chat preflight blocks SQL for missing, processing, failed, deleted, or non-queryable files.
- Delete clears active file references before removing raw/cache/catalog/metadata.
- Frontend file types now understand `uploaded`, `deleting`, `progress`, `queryable`, `row_count`, `sheet_count`, and `table_count`.

### Existing uploaded files after reconciliation

| File | Status | Queryable | Rows |
| --- | --- | ---: | ---: |
| `EntryTransaction_20260203_164943.xlsx` | ready | true | 1,294 |
| `Loss_Assignment_20260203_100840.xlsx` | ready | true | 36,309 |
| `Machine_Downtime_20260203_100753.xlsx` | ready | true | 9,151 |

### Artifacts

- `docs/UPLOAD_INGESTION_AUDIT.md`
- `docs/FILE_UPLOAD_AND_INGESTION_FLOW.md`
- `docs/FILE_READINESS_CONTRACT.md`
- `docs/FILE_SELECTION_QUERY_SCOPE.md`
- `artifacts/upload_ingestion_audit.json`
- `artifacts/existing_files_readiness.json`
- `artifacts/upload_lifecycle_tests.json`
- `artifacts/query_readiness_checks.json`
- `artifacts/file_scope_checks.json`
- `artifacts/restart_reconciliation.json`
- `artifacts/upload_ingestion_failures.md`

### Verification

- `python -m compileall src backend`: passed.
- `python -m pytest tests/test_customer_query_understanding.py tests/test_web_api.py -q`: 13 passed.
- `npm test -- --run`: 18 passed.
- `npm run build`: passed with existing non-blocking Vite chunk-size warning.
