# Frontend Message Rendering Contract

`UiMessage` is the single frontend message type for live and historical assistant messages:

- `id`
- `role`
- `content`
- optional `response`

`toUiMessages()` preserves `ConversationMessage.response` from the History API. `ChatMessage` renders text/table/chart/dashboard/sources/filters from the same component path used by live responses.

Internal debug metadata is displayed only when `VITE_SHOW_INTERNAL_DEBUG_METADATA=true`.
