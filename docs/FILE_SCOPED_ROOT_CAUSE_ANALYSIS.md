# File-Scoped Root Cause Analysis

Date: 2026-06-23

Branch: `release/customer-demo-rc1`

## Baseline

Current file-scoped benchmark baseline before this hardening round:

- Total: 320
- Passed: 266
- Failed: 54
- Accuracy: 83.13%
- Cross-file SQL count: 0
- Cross-file provenance count: 0

The detailed inventory is stored in `artifacts/file_scoped_failure_inventory.json`.

## Failure Taxonomy

| Failure category | Count | Root cause |
| --- | ---: | --- |
| `ROUTER_MODE_ERROR` | 22 | Freeform analytical/insight questions are intercepted by metadata routing or fall into generic clarification instead of executable semantic planning. |
| `BENCHMARK_ORACLE_ERROR` | 25 | The benchmark expects an analytical table/error where the product safely returns schema/refusal. These cases need oracle reconciliation, not production hardcoding. |
| `SEMANTIC_FIELD_MAPPING_ERROR` | 7 | Loss-scoped cases use downtime/machine wording, so the file-scope preflight treats them as another-file references. The planner needs scoped semantic alias mapping instead of literal workbook-name refusal for analysis terms that can map inside the active file. |

## Case Groups

- `real_llm_candidate`: 22 failures.
  - Machine anomaly questions route to `DATA_QUALITY`.
  - Loss/Entry insight questions route to `CLARIFICATION`.
- `safe_failure`: 10 failures.
  - Unsafe SQL delete requests return `REFUSAL`, while oracle expects `error`.
- `multipart`: 7 failures.
  - Loss active file plus downtime/machine wording triggers refusal before scoped semantic mapping can adapt the request.
- `context_sequence`: 15 failures.
  - Final turn is `Xem schema`; product returns schema correctly, benchmark expects table.

## File-Scope Layers Observed

- Conversation state keeps an active file and restores per-file contexts.
- Requests use `get_catalog_for_file(active_file_id)` for planner execution.
- `_plan_within_file_scope()` blocks plans outside active file tables before SQL.
- File-scoped benchmark currently reports zero cross-file SQL execution and zero cross-file provenance failures.

## Fix Strategy

Code fixes should target only production behavior gaps:

1. Route freeform analytical questions to semantic/deterministic analysis instead of metadata data-quality or generic clarification.
2. Add scoped semantic alias mapping for Loss/Entry when user says downtime/machine-like words but the active file contains equivalent fields.
3. Keep unsafe SQL as a safe customer-facing refusal unless the product contract explicitly reclassifies it as error.
4. Reconcile benchmark oracle for schema turns separately; do not make `Xem schema` return a fake analytical table.

No benchmark utterance-specific hardcoding is allowed.
