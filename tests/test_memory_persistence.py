from __future__ import annotations

import sqlite3

import pandas as pd

from src.conversation.memory_service import ConversationMemoryService
from src.conversation.state import ConversationState
from src.persistence.sqlite_store import SQLiteMemoryStore


def test_create_save_load_conversation_state(tmp_path):
    service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    state = service.create_conversation("Test")
    state.active_table = "machine_downtime"
    state.active_metrics = [{"name": "total_duration_seconds"}]
    service.save_state(state)

    loaded = service.load_conversation(state.conversation_id)

    assert loaded.conversation_id == state.conversation_id
    assert loaded.active_table == "machine_downtime"
    assert loaded.active_metrics[0]["name"] == "total_duration_seconds"


def test_turn_and_result_cache_persistence(tmp_path):
    service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    state = service.create_conversation("Cache")
    df = pd.DataFrame([{"may": "May 1", "total_duration_seconds": 10.0}])
    state.update_from_result(df)
    turn_id = service.save_turn(
        state,
        role="assistant",
        content="done",
        execution_mode="DETERMINISTIC",
        query_plan={"intent": "query"},
        result_summary=state.last_result_summary,
        result_dataframe=df,
    )

    turns = service.load_recent_turns(state.conversation_id)
    ref, cached = service.load_result_reference(state.last_result_cache_id)

    assert turn_id is not None
    assert len(turns) == 1
    assert ref is not None
    assert cached is not None
    assert cached.iloc[0]["may"] == "May 1"


def test_restore_after_session_clear_matches_original_state(tmp_path):
    service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    state = service.create_conversation("Restore")
    state.active_dimensions = ["may"]
    state.active_limit = 5
    service.save_turn(state, role="user", content="Top 5 may")
    conversation_id = state.conversation_id

    restored_service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    restored = restored_service.load_conversation(conversation_id)

    assert restored.active_dimensions == ["may"]
    assert restored.active_limit == 5


def test_multiple_conversations_reset_and_delete(tmp_path):
    service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    first = service.create_conversation("One")
    second = service.create_conversation("Two")
    first.active_table = "machine_downtime"
    service.save_state(first)

    reset = service.reset_conversation(first.conversation_id)
    service.delete_conversation(second.conversation_id)
    conversations = service.list_conversations()

    assert reset.active_table is None
    assert all(item["id"] != second.conversation_id for item in conversations)


def test_corrupted_state_json_falls_back_to_empty_state(tmp_path):
    service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    state = service.create_conversation("Corrupt")
    with sqlite3.connect(tmp_path / "memory.db") as con:
        con.execute("UPDATE conversation_states SET state_json = ? WHERE conversation_id = ?", ("{bad json", state.conversation_id))
        con.commit()

    loaded = service.load_conversation(state.conversation_id)

    assert isinstance(loaded, ConversationState)
    assert loaded.conversation_id == state.conversation_id
    assert loaded.active_table is None


def test_migration_is_idempotent(tmp_path):
    SQLiteMemoryStore(tmp_path / "memory.db")
    SQLiteMemoryStore(tmp_path / "memory.db")

    assert (tmp_path / "memory.db").exists()


def test_missing_result_parquet_returns_none_dataframe(tmp_path):
    service = ConversationMemoryService(tmp_path / "memory.db", tmp_path / "cache")
    state = service.create_conversation("Missing")
    service.save_turn(state, role="assistant", content="done")
    turn_id = state.recent_turn_ids[-1]
    store = service.store
    assert store is not None
    from src.conversation.schemas import ResultCacheRecord

    record = ResultCacheRecord(conversation_id=state.conversation_id, turn_id=turn_id, parquet_path=str(tmp_path / "missing.parquet"))
    store.save_result_cache(record)

    ref, df = service.load_result_reference(record.id)

    assert ref is not None
    assert df is None
