# LLM Invocation And Fallback Audit

## Current Routing Flow

Public chat requests flow through:

1. immutable conversation source-file validation;
2. pending clarification resolution, unless the user has started a new semantic request;
3. row-level and metadata deterministic handlers for exact customer questions;
4. semantic follow-up detector for commentary on prior results;
5. `QueryPlanner`, which runs deterministic parsing, `HybridRouter`, optional REAL_LLM semantic planning, safe validation, and query execution;
6. grounded composer for result commentary when a table/chart answer also asks for insight;
7. public response sanitizer, unless `SHOW_INTERNAL_DEBUG_METADATA=true`.

## Early Exit Rules

Allowed early exits:

- exact file/schema/sample/row-count/data-quality/provenance questions;
- exact row-level lookup questions;
- high-confidence deterministic aggregation with complete metric, dimension, ranking, filter and output coverage;
- exact pending clarification slot answers such as `Số lần dừng.`;
- source-file mismatch refusal.

Semantic rescue now runs before generic clarification for open-ended, multipart, commentary, topic-restore, and pending-state new requests.

## LLM Boundary

Actual model calls only happen in:

- `src/llm/ollama_client.py::OllamaClient.chat`
- `src/llm/ollama_client.py::OllamaClient.generate`

Planner metadata sets `llm_called` only around this boundary. The model-unavailable benchmark forces a bad endpoint and confirms the semantic route records an attempted LLM request before returning a safe fallback/error.

## Confidence Policy

Previous risk: deterministic confidence could win when keyword coverage was high but semantic requirements such as commentary, percentage, comparison or time-scope explanation were present.

Current policy:

- exact deterministic cases remain deterministic;
- semantic and multipart terms are routed to REAL_LLM before accepting a high-confidence deterministic candidate;
- explicit requirements from the question are preserved after LLM planning, including `percentage_of_total`, top-N and time filters;
- if LLM returns a clarification while a safe deterministic candidate exists, the deterministic plan is used only as a recorded post-LLM rescue.

## Fallback Policy

Fallback is internal only and never shown in customer UI/API. Allowed fallback paths:

- LLM timeout/connection/model unavailable after a request attempt;
- invalid structured output after one retry;
- LLM returns clarification even though deterministic evidence can safely satisfy the requested analytics.

Silent fallback count in the final benchmark is `0`.

## Public Metadata Policy

Customer-facing chat and history responses omit:

- `REAL_LLM`
- `DETERMINISTIC`
- `fallback`
- model name
- latency
- router confidence/reason
- execution mode

Internal QA can still run with `SHOW_INTERNAL_DEBUG_METADATA=true`.

## Final Metrics

From `artifacts/llm_invocation_final_results.json`:

- total cases: 12
- passed cases: 12
- semantic REAL_LLM call rate: 100%
- deterministic unnecessary LLM calls: 0
- silent fallback count: 0
- fallback reason coverage: 100%
- structured output validity: 100%
- LLM P50/P95 latency: 7525.0 / 9075.1 ms

From `artifacts/demo_conversation_seed_results.json`:

- demo conversations: 11
- total turns: 37
- passed turns: 37
- actual LLM calls: 2
- cross-file violations: 0
- repeated clarification loops: 0

From `artifacts/public_api_contract_results.json`:

- checked conversation details: 11
- internal metadata leaks: 0

## Regression Results

- `python -m compileall src backend scripts evaluation`: passed
- `python -m pytest -q`: 70 passed
- `python evaluation\planner_probe.py`: 60/60
- `python evaluation\run_row_level_benchmark.py`: 81/81
- `python evaluation\run_file_scoped_benchmark.py`: 320/320
- `python evaluation\run_customer_challenge_benchmark.py`: 150/150
- `python evaluation\run_black_box_customer_uat.py`: 6/6
- `python evaluation\run_response_persistence_uat.py`: passed
- `python evaluation\run_answer_quality_benchmark.py`: 13/13
- `python evaluation\run_llm_invocation_benchmark.py`: 12/12
- `python evaluation\run_public_api_contract_check.py`: passed
- `npm test -- --run`: 18 passed
- `npm run build`: passed, with the existing large chunk warning

## Artifacts

- `artifacts/llm_invocation_final_results.json`
- `artifacts/llm_fallback_audit.json`
- `artifacts/llm_call_traces.json`
- `artifacts/answer_quality_final_results.json`
- `artifacts/numeric_grounding_results.json`
- `artifacts/internal_metadata_leakage_results.json`
- `artifacts/public_api_contract_results.json`
- `artifacts/customer_answer_examples.md`
- `artifacts/demo_conversation_seed_results.json`
- `artifacts/structured_response_persistence_results.json`
