# Structured Response Persistence Audit

## Root Cause

Live `POST /messages` returned a full `ChatResponse`, but history was previously centered on `conversation_turns.content`. After refresh, rich payloads could degrade to text.

## Current Fix

`conversation_turns.response_json` stores the canonical JSON-safe `ChatResponse` snapshot for every assistant response. `GET /api/conversations/{id}` hydrates `ConversationMessage.response` from that column. The frontend maps live and historical messages into one `UiMessage` type and renders both with `ChatMessage`.

## Files

- `src/application/chat_service.py`: creates and persists final response snapshots, including internal debug metadata when enabled.
- `src/conversation/memory_service.py`: writes response payload atomically with the assistant turn and state.
- `src/persistence/sqlite_store.py`: stores/loads `response_json`.
- `frontend/src/App.tsx`: normalizes historical `response` into UI messages.

## Lost Data Before Fix

Tables, charts, dashboards, sources, filters, and debug metadata were not reliably available after reload. Legacy content-only messages remain readable as text.
