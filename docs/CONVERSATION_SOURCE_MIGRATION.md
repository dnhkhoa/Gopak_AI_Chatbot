# Conversation Source Migration

## Schema Migration

`src/persistence/migrations.py` idempotently adds these nullable columns to `conversations`:

- `source_file_id`
- `source_file_name`
- `source_file_sha256`
- `source_catalog_version`

Existing content-only and structured response history remains untouched.

## Backfill

On conversation list/detail/message processing, if an older conversation has no row-level source but its persisted `ConversationState.active_file_id` is populated, the service backfills `conversations.source_file_id` and `source_file_name`.

Mixed-file legacy conversations are not silently reassigned during reset/seed. The demo reset workflow backs up old conversations first, clears them by transaction, and seeds new public-API conversations with one source file each.

## Unknown Legacy Source

If a legacy conversation lacks source provenance entirely, it remains readable as history. New data questions require selecting a Ready file and creating/binding a new conversation.
