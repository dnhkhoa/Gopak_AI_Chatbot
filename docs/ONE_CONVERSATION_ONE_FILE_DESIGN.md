# One Conversation, One Source File Design

## Previous Behavior

Conversation source was stored in `ConversationState.active_file_id`. The `PUT /api/conversations/{id}/active-file` endpoint could replace that value on an existing conversation. That allowed messages, topics, pending clarification, charts, and response provenance from multiple workbooks to coexist in one chat.

## New Model

`conversations` now stores an immutable source binding:

- `source_file_id`
- `source_file_name`
- `source_file_sha256`
- `source_catalog_version`

`ConversationPayload` returns these fields plus `source_available`. `active_file_id` and `active_file_name` remain as compatibility aliases, but they are derived from the immutable source.

## Enforcement

`POST /api/conversations` accepts `source_file_id` and creates the conversation already bound to a Ready file. `PUT /api/conversations/{id}/active-file` is now only first-bind/idempotent:

- no source yet: bind to the requested Ready file;
- same source: success;
- different source: `409 CONVERSATION_FILE_MISMATCH`.

`POST /api/conversations/{id}/messages` rejects a mismatched `source_file_id` with the same `409` and does not persist the user message, execute SQL, or call the LLM.

## Deleted Source Files

Deleting an uploaded file no longer clears historical conversation source. Old structured response snapshots still render. New queries in that conversation return a safe failure telling the user to start a new chat with another file.
