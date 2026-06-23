# Updated One-File Benchmark Design

Date: 2026-06-23

How `run_customer_challenge_benchmark.py` and `run_black_box_customer_uat.py` model
**one conversation = one immutable source file** after the architecture change.

## Principle

A case may reference several files, but each file is exercised in its **own** conversation.
Switching files = create (or reopen) that file's conversation. The product rejects a mismatched
file with `CONVERSATION_FILE_MISMATCH` (409); benchmarks assert this rather than avoid it.

## customer_challenge

- Per case, a `conv_for(file_key)` map lazily creates one conversation per file (bound via
  `set_active_file`). A turn's `select_file` switches to / reopens that file's conversation.
- Each turn asserts the active file matches the file-bound conversation (`file_ok`); violations
  increment `isolation.cross_file_violations`.
- Cross-conversation message overlap is tracked (must stay 0).
- An explicit guard creates a machine-bound conversation and asserts both `set_active_file(loss)`
  and `process_message(..., source_file_id=loss)` raise `CONVERSATION_FILE_MISMATCH`
  (`mismatch_rejected_rate` must be 1.0).
- `file_a_b_c_a` cases now mean: query File A (conv A), then File B (conv B), File C (conv C),
  then reopen conv A and continue — proving per-file isolation + context restore on reopen.

## black_box UAT (`_uat_file_switching` → file isolation)

Four sub-cases over the public HTTP API:
1. `switch_creates_new_conversation` — File B selection creates C2; C1 unchanged; each keeps its
   own `source_file_id`.
2. `reopen_keeps_source` — reopening C1 still answers within File A.
3. `mismatch_rejected_409` — `POST` File B context into C1/File A → 409; message count unchanged
   (nothing persisted).
4. `pending_clarification_isolation` — C1 pending clarification does not leak to C2; C1 resumes on
   reopen.

## Results (2026-06-23)

- customer_challenge: 150/150; isolation `{cross_file_violations:0, cross_conversation_overlap:0,
  mismatch_rejected:2/2, pending_clarification_leakage:0}`.
- black_box UAT: file-isolation flow passes all four sub-cases; the existing basic / clarification /
  topic-restoration / restart / delete-guard flows remain.
