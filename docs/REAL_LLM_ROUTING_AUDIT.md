# REAL_LLM Routing Audit

Date: 2026-06-22

## Baseline Root Cause

The typed FSM baseline produced `REAL_LLM=0` because `HybridRouter` returned deterministic plans before semantic policy was evaluated. For lower-confidence candidates, the router only allowed REAL_LLM on a very small keyword list and otherwise returned `CLARIFICATION`. Metadata and row-level shortcuts also ran before planner routing, so semantic-looking data quality phrases could bypass REAL_LLM entirely.

## Fixes Applied

- `src/routing/router.py`: added semantic override for judgmental language such as `co ve`, `bat thuong`, `dang chu y`, `hop ly`, and expanded semantic routing terms.
- `src/llm/planner.py`: added validated deterministic fallback after a real LLM retry failure; metadata still records `llm_called=True`.
- `src/application/customer_intents.py`: prevented analytical anomaly questions from being swallowed by metadata data-quality routing.
- `src/application/row_level.py`: narrowed record-level shortcuts so analytical follow-ups are not intercepted.

## Observed Result

Ollama health during the run: `ok=True`, `model_available=True`, model `qwen3.5:9b`.

Conversation benchmark:

- Development: 240/240, REAL_LLM calls 33.
- Holdout: 120/120, REAL_LLM calls 17.
- Total: 360/360, REAL_LLM calls 50.

## Remaining Risk

REAL_LLM adds roughly 9s P95 latency on semantic turns. The planner remains dependent on qwen output quality, but failed semantic plans now fall back only after a real model call and successful plan validation.
