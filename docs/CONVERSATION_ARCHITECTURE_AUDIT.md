# Conversation Architecture Audit

Updated: 2026-06-22

## Baseline Reproduction

Production API baseline is stored in `artifacts/conversation_architecture_baseline.json`.

Observed:

- Conversation ID stayed stable.
- `llm_calls = 0`.
- The same generic clarification repeated multiple times.
- Short answers such as `tổng`, `5`, and `máy` were routed as standalone messages because no pending clarification state existed.

## Current State

Conversation state is persisted as JSON in SQLite through:

- `src/conversation/state.py`
- `src/conversation/memory_service.py`
- `src/persistence/sqlite_store.py`

`ConversationState` currently stores:

- active file id/name;
- untyped `file_contexts: dict[str, dict]`;
- last plan/result/entity hints;
- flat current analytical context fields;
- untyped `topic_frames: list[dict]`.

There is no typed `PendingClarification` model and no first-class slot filling flow.

## Message History

Turns are persisted in `conversation_turns`. State snapshots are persisted in `conversation_states`.

The router/planner do not receive a structured pending clarification object. They mainly receive the latest `ConversationState`.

## File-Scoped Memory

File context save/restore exists:

- `ConversationState.save_file_context()`
- `ConversationState.restore_file_context(file_id)`

It stores analytical fields per file, but the values are untyped dicts and pending clarification is not scoped per file.

## Router And REAL_LLM

Current flow:

`ChatApplicationService.process_message`
-> file preflight
-> row-level shortcut
-> customer metadata intent shortcut
-> `QueryPlanner.plan`
-> `StateMerger`
-> `DeterministicPlanner`
-> `HybridRouter`
-> optional REAL_LLM

REAL_LLM is called only when `HybridRouter` returns `requires_llm=True` and Ollama is healthy. In the reproduced baseline, the router returned `CLARIFICATION`, so REAL_LLM was not invoked.

## Generic Catch-All

The main generic clarification is in `src/routing/router.py`:

`Bạn muốn hỏi về tổng, đếm, top, thời gian, máy hay nguyên nhân nào?`

It is emitted when no deterministic plan is safe and the router does not classify the message as semantic enough for REAL_LLM.

## Evaluation Path

Some evaluations call `ChatApplicationService`, which is close to production. Older probes call `QueryPlanner` directly and bypass API/file preflight/UI conversation behavior.

## Keep

- Excel ingestion.
- Header detection.
- Catalog.
- DuckDB executor.
- Safe SQL builder.
- File upload lifecycle.
- QueryPlan validation.
- Rendering components.

## Replace Or Extend

- Add typed pending clarification state.
- Add file-scoped topic frames.
- Add a resolver that runs before normal router.
- Add explicit topic restoration.
- Add benchmark through `ChatApplicationService` / API-like production path.

## Candidate Assessment

Candidate A, a custom typed state machine, has the lowest migration risk because the project already persists Pydantic state in SQLite.

Candidate B, LangGraph Functional API, offers checkpoint/replay benefits but adds dependency and migration risk. Current SQLite persistence already solves the minimum restart requirement.

Candidate C, PydanticAI/Pydantic Graph, fits typed outputs but does not give a clear persistence/checkpoint advantage here without extra framework integration.

## Migration Risk

The highest risk is not framework choice; it is keeping the resolver and state transitions centralized so clarification/topic logic does not become scattered across router, planner, and renderer.
