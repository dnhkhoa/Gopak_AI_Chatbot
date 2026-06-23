# Structured Response Database Migration

## Migration

`run_migrations()` is idempotent and adds:

- `conversation_turns.response_json`
- immutable source columns on `conversations`

The migration does not delete conversations, messages, uploaded files, parquet cache, data catalog, or ingestion metadata.

## Legacy Handling

Assistant turns without `response_json` are treated as legacy content-only messages. The system does not parse text to recreate charts or tables.

## Backup

The demo reset workflow creates verified SQLite backups in `backups/demo_reset/<timestamp>/` before deleting conversation rows. Restore is available through `scripts/restore_demo_conversation_backup.py`.
