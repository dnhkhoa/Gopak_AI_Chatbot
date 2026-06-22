# Conversation Architecture Decision

Updated: 2026-06-22

## Decision

Selected candidate for implementation: Candidate A, custom typed state machine.

## Why

The current application already uses Pydantic state, SQLite persistence, FastAPI, and a centralized `ChatApplicationService`. The observed failure is not missing graph infrastructure; it is missing typed pending clarification and topic state transitions.

Candidate A changes the smallest surface area while preserving query safety and file scope.

## Candidate A

Pros:

- No new dependency.
- Reuses SQLite persistence.
- Reuses existing QueryPlan, validator, SQL builder, executor, and renderer.
- Fastest path to fix short-answer clarification loops.

Cons:

- Debug trace must be built explicitly.
- State transition discipline must be kept centralized.

## Candidate B

LangGraph Functional API was not selected for this iteration.

Reason:

- Useful checkpoint/replay model, but current SQLite state already provides restart persistence.
- Adds dependency and migration risk before proving the resolver model.
- Would not fix slot-state absence by itself.

## Candidate C

PydanticAI/Pydantic Graph was not selected for this iteration.

Reason:

- Good type fit, but persistence/interruption semantics would still need project-specific work.
- Ollama + structured QueryPlan integration already exists.

## Weighted Matrix

See `artifacts/conversation_architecture_decision_matrix.csv`.

## Benchmark Result

Candidate A was implemented as the continuation path and evaluated on 240 production-path conversation sequences:

- Passed: 140/240.
- Accuracy: 58.33%.
- Repeated clarification loops: 20.
- P50/P95 latency: 44.7 ms / 152.4 ms.
- REAL_LLM calls observed: 0.

This fails the release threshold. The result is useful because it proves the selected direction can fix simple short-answer slot filling, while also exposing remaining blockers in topic restoration, semantic LLM routing, and broader multi-part coverage.

## Release Position

Release gate: `NOT_READY`.

Candidate A remains the recommended continuation path, but not a production-ready implementation.
