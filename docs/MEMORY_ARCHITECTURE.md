# Memory Architecture

Updated: 2026-06-21

## Design

The app now uses a local layered memory model:

- `st.session_state`: hot UI cache only (`conversation_id`, `conversation_state`, `messages`).
- `ConversationState`: Pydantic structured analytical state.
- SQLite: durable conversations, turns, state JSON, and result-cache references.
- Parquet result cache: large tabular results under `cache/conversations/<conversation_id>/<turn_id>.parquet`.

No Redis, vector database, cloud storage, or DuckDB transactional chat store is used.

## SQLite

Default path:

- `data/app_memory.db`

Tables:

- `conversations`
- `conversation_turns`
- `conversation_states`
- `result_cache`

Migrations are idempotent and enable `PRAGMA foreign_keys = ON`.

## Service API

Streamlit goes through `ConversationMemoryService`:

- `create_conversation()`
- `load_conversation(conversation_id)`
- `save_turn(...)`
- `save_state(state)`
- `reset_conversation(conversation_id)`
- `delete_conversation(conversation_id)`
- `list_conversations()`
- `load_recent_turns(conversation_id, limit=6)`
- `load_result_reference(cache_id)`

If SQLite fails, the service marks `persistence_degraded=true` and returns session-only state instead of crashing the app.

## State

`ConversationState` tracks:

- active table, metrics, dimensions, filters, time range, having, ranking, sort, limit, output.
- last entities such as `top_machine`, `top_loss_name`, `top_group`.
- last result summary and result-cache id.
- recent turn ids and conversation summary placeholder.

Mutable defaults use `Field(default_factory=...)`.

## Safety

- SQLite stores state/turn metadata and result references only.
- DataFrames are not stored in SQLite.
- Raw Excel data is not duplicated into memory DB.
- Model chain-of-thought is not stored.
- Large result tables are cached as parquet files and referenced by id.
