# Root-Cause Audit — Localization, Active-File Capability, and Error/Health

Scope: explains why three P0 classes of defect recur in Gopak, and maps **every customer-facing response path** to the exact place it sources display labels, error messages, source metadata, capability validation, and health status. This is the audit that motivates the unified gates introduced alongside it.

Date: 2026-06-25. Branch: `feature/demo-conversation-seeding`. Baseline commit: `ad1cfff`.

---

## 0. The three P0s in one sentence each

- **P0-A (localization leak):** un-accented Vietnamese (`Tong quan du lieu`, `PHAT HIEN`) and internal snake_case keys (`transaction_count`, `gia_tri_can`) reach the UI because some response builders hand-type ASCII strings or fall back to raw normalized keys, and there is **no gate** that inspects the final response for leaks.
- **P0-B (wrong-file generic error):** a question the active file cannot answer (downtime on a transaction file) is **planned and executed anyway**; when planning/SQL fails it is caught by one broad `except Exception` and reported as the generic English `The analysis service could not complete this request.` There is **no capability gate before the planner**.
- **P0-C (everything looks degraded / English errors):** health is a single `status: ok|degraded` boolean driven solely by `persistence_degraded`; any persistence hiccup (or, in the frontend, model-unavailable) flips a global "Some services are degraded" banner. Business-level rejections (schema mismatch, ambiguous input) are not separated from infrastructure outages, and the catch-all error message is English.

---

## 1. The response paths (why fixes don't stick)

`ChatApplicationService.process_message` ([src/application/chat_service.py](../src/application/chat_service.py)) is the single entry, but it dispatches to **independent builders**, each of which historically chose its own labels / error text / metadata shape:

| # | Path | Builder | Where it gets display labels | Where it gets error text | Source metadata | Capability check | Health signal |
|---|------|---------|------------------------------|--------------------------|-----------------|------------------|---------------|
| 1 | deterministic / planner success | `build_presented_response` → `_response_from_presented` | `formatters.humanize_column_name` + `COLUMN_LABELS` | n/a | `_sources_for_plan` | none (only `_plan_within_file_scope` table check) | `persistence_degraded` in metadata |
| 2 | semantic follow-up | `_try_semantic_followup_response` | composer text (LLM) + presented | LLM-generation English string (`The language model could not generate…`) | inherited | none | — |
| 3 | commentary | `_generate_grounded_commentary` | appends to presented summary | same LLM English string | inherited | none | — |
| 4 | open-ended analysis | `_try_open_ended_analysis_response` / `overview_analysis` | **hand-typed strings** in `overview_analysis._generic_candidates` (some un-accented), else `humanize_column_name` | n/a | inherited | none | — |
| 5 | chart | `build_chart` + presented | `humanize_column_name` for axis labels | coverage gate → English `Unable to build a chart…` | `_sources_for_plan` | coverage_for_plan only | — |
| 6 | report | `_try_report_orchestration_response` + exporters | `humanize_column_name` | English `Unable to build a report…` | sources | coverage only | — |
| 7 | metadata intents (overview/schema/rowcount/quality) | `_try_metadata_response` | mixed; overview uses `overview_analysis` | n/a | catalog | none | — |
| 8 | fallback / exception | `except Exception` at chat_service.py:677 | n/a | **English** `The analysis service could not complete this request.` | partial | none | sets `file_scope_validated=False` |
| 9 | History reload | `get_conversation` → `_stored_chat_response` | re-hydrates stored `response_json` (no re-render, so as-stored) | as-stored | as-stored | none | — |

Consequences:
1. **No single label resolver.** `COLUMN_LABELS` lives in [src/rendering/formatters.py](../src/rendering/formatters.py) and only covers ~20 known columns; everything else falls through `humanize_column_name`'s final branch `column.replace("_"," ")` → `transaction_count` → `"Transaction count"` (English) and `sum_gia_tri_can` → `"Sum gia tri can"` (un-accented). Path 4 bypasses even that with literals.
2. **No public serialization gate.** Nothing inspected the assembled `ChatResponse` for snake_case / missing-diacritic / leaked-enum text before returning it. (`routes_chat.py` already calls an optional `service.public_chat_response` hook — it was a no-op because the method did not exist.)
3. **Normalization reused for presentation.** `query_understanding/text.normalize_text` and `ingestion/normalizer.strip_accents` are routing/matching helpers, but their snake_case/ASCII output is what reaches the UI whenever a display label is missing.
4. **Capability validation is not a gate.** The only pre-planner check is `_plan_within_file_scope` (does the plan reference an allowed *table*) — it cannot catch "this file has no `machine`/`downtime` columns", because the planner may still emit a syntactically valid plan that explodes at SQL time.
5. **One `except` for business + infra.** chat_service.py:677 collapses capability/validation/timeout/model/persistence failures into one English message and a vaguely-degraded metadata blob.
6. **Tests run per-feature.** No end-to-end "ask a downtime question on a transaction file and assert the customer sees a Vietnamese unsupported-file message, no SQL, no degraded banner" test existed, so regressions in any single path went unnoticed.

---

## 2. Localization (P0-A) — exact leak points

- [src/application/overview_analysis.py:620-626](../src/application/overview_analysis.py) `_generic_candidates` date-range candidate: literal `"Pham vi thoi gian"`, `"Du lieu bao phu khoang thoi gian nao?"`, `"Du lieu co pham vi thoi gian tu … den …"` — **hand-typed without diacritics.**
- [src/rendering/formatters.py:93-94](../src/rendering/formatters.py) `humanize_column_name` fallback: returns title-cased snake form → English / un-accented for any column not in `COLUMN_LABELS` and not in catalog `original_name`.
- [src/catalog/profiler.py:80-82](../src/catalog/profiler.py) auto-generated metric names `sum_{col}` / `avg_{col}` are snake_case; if not in `COLUMN_LABELS` they surface as `"Sum gia tri can"`.
- The uppercase `PHAT HIEN` / `DOI TUONG` / `CHI SO` / `GIA TRI` from the screenshot come from a presentation layer upper-casing an already-un-accented heading; the root fix is to never produce the un-accented heading in the first place and to validate the final response.

Root cause: **display label is not a first-class, single-sourced concept** distinct from canonical/normalized/source names, and there is no validator backstop.

---

## 3. Capability (P0-B)

- No `RequestRequirements` (what the question needs) and no `DatasetCapabilityProfile` (what the file offers) existed.
- `process_message` goes user → intent → planner → SQL with only `_plan_within_file_scope` (table membership) in between. A downtime question on `EntryTransaction` produces a plan referencing non-existent columns/metrics; `SafeQueryExecutor.execute` raises; caught at chat_service.py:677 → generic English error → (if a persistence write hiccups) degraded banner.
- Expected behavior is `UNSUPPORTED_BY_ACTIVE_FILE`: classify **before** planning, never touch SQL/LLM, return a Vietnamese message naming the missing dimensions/metrics and recommending the right file.

---

## 4. Error taxonomy & health (P0-C)

- [src/application/schemas.py:145-151](../src/application/schemas.py) `HealthStatus` = `status: ok|degraded` + four booleans. `status` is `degraded` iff `memory_available` is false (chat_service.py:142-152).
- [frontend ConversationSidebar.tsx:132](../frontend/src/features/conversations/ConversationSidebar.tsx) banner fires on `!ollama_available || !memory_available` — i.e. a model outage **or** any persistence degrade shows the global English "Some services are degraded".
- `memory_service._degrade()` ([src/conversation/memory_service.py:229](../src/conversation/memory_service.py)) sets `persistence_degraded=True` in every DB catch block, so a transient write error during an *unrelated* failed turn can flip global health.
- All exceptions collapse to the English string at chat_service.py:677-692; there is no error-code taxonomy and no Vietnamese customer-error registry.

Root cause: **health is a global boolean, not per-component**, and **business rejections share an exception channel with infrastructure faults**, and the **customer error copy is English and generic**.

---

## 5. Fix strategy (single sources of truth)

1. **`src/rendering/labels.py`** — `FieldIdentity` (canonical/normalized/display_name_vi/source) + `DisplayLabelRegistry` as the *only* label resolver. `formatters.humanize_column_name` delegates to it; its fallback is a Vietnamese-safe label, never raw snake_case / ASCII for known semantic roles, and metric prefixes (`sum_`/`avg_`/`total_`) resolve through it.
2. **`src/application/capability.py`** — `RequestRequirements`, `DatasetCapabilityProfile`, `ActiveFileCapabilityGate`. One gate, called before the planner.
3. **`src/application/errors.py`** — `ErrorCode` taxonomy + `GopakError` hierarchy + `CustomerErrorMessagePolicy` (Vietnamese). The catch-all classifies into a code and renders the policy message; trace stays internal.
4. **`src/application/public_response.py`** — `PublicResponseSanitizer` running `LocalizationValidator` + `MetadataLeakageValidator` over every response, wired through the already-present `service.public_chat_response` hook.
5. **Layered `ServiceHealth`** — per-component status; the customer banner only reflects true infrastructure faults, and is Vietnamese. Schema mismatch / capability rejection never change health.
6. **Contract tests** across all paths (localization, capability, error, health) so a regression in any single builder fails CI.

Each section above lists the concrete file:line so the gates can be verified to actually intercept every path rather than patching one screenshot.
