# Outdated Multi-File Benchmark Audit

Date: 2026-06-23 · Branch: `feature/demo-conversation-seeding`

Two benchmarks failed after the product adopted **one conversation = one immutable source file**.
The failures were correct product behavior (HTTP 409 / `CONVERSATION_FILE_MISMATCH`), not regressions.
This documents the outdated scenarios and the rewrite.

## Product rule (unchanged, must keep)

- `conversation.source_file_id` is immutable once bound.
- A request whose file context differs from the conversation's source → `CONVERSATION_FILE_MISMATCH`
  → HTTP 409, **no SQL, no LLM, no message persisted, no state mutation**.
- Selecting another file = create a **new** conversation bound to that file.

## `evaluation/run_customer_challenge_benchmark.py`

| Item | Detail |
| --- | --- |
| Scenario | Category `file_a_b_c_a` (15 cases) |
| Old behavior | One `conversation_id`; per-turn `select_file` called `app.set_active_file(conv, otherFile)` to switch machine→loss→entry→machine in the same conversation. |
| Why incompatible | `set_active_file` on a conversation already bound to another file now raises `CONVERSATION_FILE_MISMATCH`. |
| New expected behavior | Each file gets its own conversation; switching files creates/reopens that file's conversation; reopening the first file continues its context. |
| Files/functions updated | `run()` loop (per-case `conv_for(file_key)` map), `_select` → `_record`, added isolation metrics + explicit mismatch-rejection assertion. |

## `evaluation/run_black_box_customer_uat.py`

| Item | Detail |
| --- | --- |
| Scenario | `_uat_file_switching` |
| Old behavior | One conversation; `_select_file` switched machine→loss→entry→machine via `PUT /active-file`. |
| Why incompatible | The second `PUT /active-file` to a different file → 409. |
| New expected behavior | Four sub-cases (below). |
| Files/functions updated | `_uat_file_switching` rewritten; added `_conversation`, `_messages`, `_send_mismatch` helpers. |

### New black-box sub-cases
1. **switch_creates_new_conversation** — File B selection makes C2; C1/File A unchanged; each conversation keeps its own `source_file_id`.
2. **reopen_keeps_source** — reopening C1 still answers within File A.
3. **mismatch_rejected_409** — posting File B context into C1/File A → 409, message count unchanged (nothing persisted).
4. **pending_clarification_isolation** — C1 pending clarification does not leak to C2; C1 resumes its pending flow on reopen.

## Assertions added (both benchmarks)
- conversation source immutable / file-bound
- new file → new conversation
- cross-conversation message overlap = 0
- cross-file violations = 0
- mismatch rejected = 100%
- pending clarification leakage = 0
- the `409` mismatch test is preserved as correct behavior (never relaxed).
