# Demo Conversation Data Audit

## Storage

- Database path: `D:\Gopak Chatbot\data\app_memory.db`
- Storage type: SQLite
- Runtime owner: `ConversationMemoryService` with `SQLiteMemoryStore`
- Config key: `Settings.memory_db_path`

## Conversation Tables

The current SQLite schema contains these conversation-related tables:

| Table | Purpose | Current count before reset |
| --- | --- | ---: |
| `conversations` | Sidebar/history records, titles, status, created/updated timestamps | 1616 |
| `conversation_turns` | User/assistant/system messages, execution mode, query plan, result summary, stored response payload | 5628 |
| `conversation_states` | Serialized `ConversationState`, including active file, file contexts, topic frames, pending clarification | 1616 |
| `result_cache` | Conversation result-cache references for assistant table/chart turns | 1031 |

## Foreign Keys

- `conversation_turns.conversation_id` references `conversations.id`
- `conversation_states.conversation_id` references `conversations.id`
- `result_cache.conversation_id` references `conversations.id`

There is no cascade delete in the schema, so child rows must be deleted before parent rows.

## State Contents

`conversation_states.state_json` stores:

- active file id/name;
- per-file scoped conversation context;
- topic frames;
- pending clarification;
- current and last query plan;
- active metrics, dimensions, filters, time range, ranking, output;
- recent turn ids;
- last result cache reference.

## Delete Order

Use one SQLite transaction:

1. `DELETE FROM result_cache`
2. `DELETE FROM conversation_turns`
3. `DELETE FROM conversation_states`
4. `DELETE FROM conversations`
5. verify all four counts are zero
6. commit

Rollback on any failure.

## Backup Procedure

`scripts/reset_demo_conversations.py --backup --confirm-reset` copies only the conversation SQLite database into:

`backups/demo_reset/<timestamp>/app_memory.db`

It writes `backup_manifest.json` with source paths, backup paths, SHA-256, SQLite integrity result, and Git commit. Uploaded Excel files, uploaded metadata, data catalog, ingestion manifest, and parquet analytics cache are intentionally not copied or modified.

## Restore Procedure

`scripts/restore_demo_conversation_backup.py --backup-dir backups/demo_reset/<timestamp> --confirm-restore`

Before restore, the script backs up the current conversation DB into `backups/demo_restore/<timestamp>/`. It then copies the selected backup DB back to `data/app_memory.db`, runs SQLite integrity check, and writes `artifacts/restore_demo_conversation_report.json`.

## Files Not Deleted

- `data/uploaded_files.json`
- `data/uploads/`
- `cache/data_catalog.json`
- `cache/manifest.json`
- `cache/tables/`
- source Excel workbooks
- frontend build artifacts
