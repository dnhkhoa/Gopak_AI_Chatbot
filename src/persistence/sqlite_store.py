from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.conversation.schemas import ConversationRecord, ConversationTurn, ResultCacheRecord, utc_now_iso
from src.conversation.state import ConversationState
from src.persistence.migrations import run_migrations


class SQLiteMemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            run_migrations(con)

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=1.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def create_conversation(
        self,
        title: str | None = None,
        *,
        source_file_id: str | None = None,
        source_file_name: str | None = None,
        source_file_sha256: str | None = None,
        source_catalog_version: str | None = None,
    ) -> ConversationRecord:
        record = ConversationRecord(
            title=title or "Hoi thoai moi",
            source_file_id=source_file_id,
            source_file_name=source_file_name,
            source_file_sha256=source_file_sha256,
            source_catalog_version=source_catalog_version,
        )
        with self.connect() as con:
            with con:
                con.execute(
                    """
                    INSERT INTO conversations
                    (id, title, source_file_id, source_file_name, source_file_sha256, source_catalog_version, created_at, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.title,
                        record.source_file_id,
                        record.source_file_name,
                        record.source_file_sha256,
                        record.source_catalog_version,
                        record.created_at,
                        record.updated_at,
                        record.status,
                    ),
                )
        return record

    def list_conversations(self) -> list[ConversationRecord]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT id, title, source_file_id, source_file_name, source_file_sha256, source_catalog_version, created_at, updated_at, status
                FROM conversations
                WHERE status <> 'deleted'
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [ConversationRecord(**dict(row)) for row in rows]

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        source_file_id: str | None = None,
        source_file_name: str | None = None,
        source_file_sha256: str | None = None,
        source_catalog_version: str | None = None,
    ) -> None:
        current = self.get_conversation(conversation_id)
        if not current:
            return
        if source_file_id and current.source_file_id and current.source_file_id != source_file_id:
            raise ValueError("CONVERSATION_FILE_MISMATCH")
        with self.connect() as con:
            with con:
                con.execute(
                    """
                    UPDATE conversations
                    SET title = ?,
                        status = ?,
                        source_file_id = ?,
                        source_file_name = ?,
                        source_file_sha256 = ?,
                        source_catalog_version = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title or current.title,
                        status or current.status,
                        source_file_id if source_file_id is not None else current.source_file_id,
                        source_file_name if source_file_name is not None else current.source_file_name,
                        source_file_sha256 if source_file_sha256 is not None else current.source_file_sha256,
                        source_catalog_version if source_catalog_version is not None else current.source_catalog_version,
                        utc_now_iso(),
                        conversation_id,
                    ),
                )

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT id, title, source_file_id, source_file_name, source_file_sha256, source_catalog_version, created_at, updated_at, status
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return ConversationRecord(**dict(row)) if row else None

    def save_turn_and_state(
        self,
        turn: ConversationTurn,
        state: ConversationState,
        summary: str | None = None,
    ) -> None:
        state_json = state.model_dump_json()
        with self.connect() as con:
            with con:
                con.execute(
                    """
                    INSERT INTO conversation_turns
                    (id, conversation_id, turn_index, role, content, execution_mode, query_plan_json, result_summary_json, response_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        turn.id,
                        turn.conversation_id,
                        turn.turn_index,
                        turn.role,
                        turn.content,
                        turn.execution_mode,
                        turn.query_plan_json,
                        turn.result_summary_json,
                        turn.response_json,
                        turn.created_at,
                    ),
                )
                con.execute(
                    """
                    INSERT INTO conversation_states (conversation_id, state_json, summary, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(conversation_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        summary = excluded.summary,
                        updated_at = excluded.updated_at
                    """,
                    (state.conversation_id, state_json, summary, utc_now_iso()),
                )
                con.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now_iso(), state.conversation_id))

    def save_state(self, state: ConversationState, summary: str | None = None) -> None:
        with self.connect() as con:
            with con:
                con.execute(
                    """
                    INSERT INTO conversation_states (conversation_id, state_json, summary, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(conversation_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        summary = excluded.summary,
                        updated_at = excluded.updated_at
                    """,
                    (state.conversation_id, state.model_dump_json(), summary, utc_now_iso()),
                )

    def load_state(self, conversation_id: str) -> ConversationState | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT state_json FROM conversation_states WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if not row:
            return None
        try:
            return ConversationState.model_validate_json(row["state_json"])
        except Exception:
            return ConversationState(conversation_id=conversation_id)

    def next_turn_index(self, conversation_id: str) -> int:
        with self.connect() as con:
            value = con.execute(
                "SELECT COALESCE(MAX(turn_index), 0) + 1 AS next_idx FROM conversation_turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["next_idx"]
        return int(value)

    def load_recent_turns(self, conversation_id: str, limit: int = 6) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT id, conversation_id, turn_index, role, content, execution_mode, query_plan_json, result_summary_json, response_json, created_at
                FROM conversation_turns
                WHERE conversation_id = ?
                ORDER BY turn_index DESC
                LIMIT ?
                """,
                (conversation_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def save_result_cache(self, record: ResultCacheRecord) -> None:
        with self.connect() as con:
            with con:
                con.execute(
                    """
                    INSERT INTO result_cache (id, conversation_id, turn_id, parquet_path, row_count, schema_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.conversation_id,
                        record.turn_id,
                        record.parquet_path,
                        record.row_count,
                        record.result_schema_json,
                        record.created_at,
                    ),
                )

    def load_result_reference(self, cache_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM result_cache WHERE id = ?", (cache_id,)).fetchone()
        return dict(row) if row else None

    def reset_conversation(self, conversation_id: str) -> ConversationState:
        state = ConversationState(conversation_id=conversation_id)
        self.update_conversation(conversation_id, status="reset")
        self.save_state(state)
        return state

    def delete_conversation(self, conversation_id: str) -> None:
        self.update_conversation(conversation_id, status="deleted")

    def snapshot(self) -> dict[str, Any]:
        with self.connect() as con:
            counts = {
                table: con.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
                for table in ["conversations", "conversation_turns", "conversation_states", "result_cache"]
            }
        return {"db_path": str(self.db_path), "counts": counts}


def dumps_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)
