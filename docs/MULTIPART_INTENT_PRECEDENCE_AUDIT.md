# Multi-Part Intent Precedence Audit

Date: 2026-06-23 · Branch: `feature/demo-conversation-seeding`

## Symptom

> Cho tôi top 5 nhóm có số lần ghi nhận cao nhất, thêm tỷ lệ phần trăm và nhận xét những điểm đáng chú ý trong kết quả.

returned a generic clarification:

> Bạn muốn mình nhận xét dựa trên kết quả nào?

despite the question fully specifying dimension (nhóm), metric (số lần ghi nhận), limit (5),
derived metric (tỷ lệ phần trăm) and outputs (table + commentary).

## Root causes

1. **`_try_semantic_followup_response` hijack** (`src/application/chat_service.py`).
   It runs *before* the planner and fired on any message containing commentary words
   (`nhan xet`, `insight`, `giai thich`, ...). With no prior result it returned the generic
   clarification — so a trailing "và nhận xét" stole the whole intent.

2. **`_freeform_insight_plan` greediness** (`src/query_understanding/deterministic_planner.py`).
   It also keyed on `nhan xet`/`insight`/`quan trong`/`tom tat`/`phan tich` and mapped to a
   **duration** ranking, ignoring an explicitly requested count metric, percentage, and time range.
   This made "số lần ghi nhận" come back as downtime hours and dropped "tháng gần nhất".

## Precedence — before vs after

Before: `commentary keyword` (semantic follow-up) → hijacks → clarification. Output/commentary
modifiers could override the core analytical request.

After (correct order):
1. Resolve core analytical request (dimension, metric, aggregation).
2. Resolve filters / time range.
3. Resolve ranking / limit.
4. Resolve derived metrics (percentage, share).
5. Resolve requested presentation/output (table, chart, commentary).
6. Clarify only truly-missing required slots.

Commentary/chart are treated as **modifiers layered on the result**, never as the whole intent.

## Fixes

- `_try_semantic_followup_response`: only treats the turn as follow-up-only commentary when it
  does **not** carry a new analytical request (`_has_new_analytics_request`) or it explicitly
  references a prior result (`_references_prior_result`). Helpers are general (ranking words +
  dimension nouns + metric words + `top N` + `theo <dim>`), not hardcoded sentences.
- Analytics turns that also request commentary get 1–3 grounded observations appended
  (`_generate_grounded_commentary`, LLM, grounded on the just-computed result; no new numbers,
  no SQL).
- `_freeform_insight_plan`: defers to the structured detectors when the question already has an
  explicit structure (`top N`, `theo`, percentage, count, or time range). It remains the fallback
  only for genuinely vague commentary requests (e.g. "phân tích giúp tôi").

## Verified (live API, diacritic Vietnamese)

| Question | Result |
| --- | --- |
| top 5 nhóm số lần ghi nhận + % + nhận xét | table+chart, count, 74,06%, commentary |
| top 5 máy tổng downtime + số lần dừng + biểu đồ | table+chart, multi-metric |
| top 3 loại tổn thất + tỷ lệ + giải thích | table, count, commentary |
| vẽ biểu đồ top 5 máy downtime | chart |
| nhận xét bảng vừa rồi (follow-up) | REAL_LLM commentary (preserved) |
| nhận xét top 5 máy downtime tháng gần nhất | table+chart, time filter applied, commentary |

File-scoped benchmark stayed 320/320 (real_llm_candidate 30/30) after every change.
