from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.conversation.schemas import ConversationTurn
from src.conversation.state import ConversationState
from src.persistence.result_cache import ResultCache
from src.persistence.sqlite_store import SQLiteMemoryStore, dumps_json


class ConversationMemoryService:
    def __init__(self, db_path: Path, cache_root: Path, recent_turns_limit: int = 6, enabled: bool = True):
        self.enabled = enabled
        self.recent_turns_limit = recent_turns_limit
        self.persistence_degraded = False
        self.last_error: str | None = None
        self.store: SQLiteMemoryStore | None = None
        self.result_cache = ResultCache(cache_root)
        if enabled:
            try:
                self.store = SQLiteMemoryStore(db_path)
            except Exception as exc:
                self.persistence_degraded = True
                self.last_error = str(exc)

    def create_conversation(self, title: str | None = None) -> ConversationState:
        if not self.store:
            return ConversationState()
        try:
            record = self.store.create_conversation(title=title)
            state = ConversationState(conversation_id=record.id)
            self.store.save_state(state, summary=state.conversation_summary)
            return state
        except Exception as exc:
            self._degrade(exc)
            return ConversationState()

    def load_conversation(self, conversation_id: str) -> ConversationState:
        if not self.store:
            return ConversationState(conversation_id=conversation_id)
        try:
            state = self.store.load_state(conversation_id)
            return state or ConversationState(conversation_id=conversation_id)
        except Exception as exc:
            self._degrade(exc)
            return ConversationState(conversation_id=conversation_id)

    def save_turn(
        self,
        state: ConversationState,
        role: str,
        content: str,
        execution_mode: str | None = None,
        query_plan: dict | None = None,
        result_summary: dict | None = None,
        response_payload: dict | None = None,
        result_dataframe: pd.DataFrame | None = None,
    ) -> str | None:
        if not self.store:
            return None
        try:
            turn = ConversationTurn(
                conversation_id=state.conversation_id,
                turn_index=self.store.next_turn_index(state.conversation_id),
                role=role,
                content=content,
                execution_mode=execution_mode,
                query_plan_json=dumps_json(query_plan),
                result_summary_json=dumps_json(result_summary),
                response_json=dumps_json(response_payload),
            )
            if result_dataframe is not None:
                cache_record = self.result_cache.save_dataframe(state.conversation_id, turn.id, result_dataframe)
                if cache_record:
                    self.store.save_result_cache(cache_record)
                    state.last_result_cache_id = cache_record.id
            if turn.id not in state.recent_turn_ids:
                state.recent_turn_ids.append(turn.id)
                state.recent_turn_ids = state.recent_turn_ids[-self.recent_turns_limit :]
            self.store.save_turn_and_state(turn, state, summary=state.conversation_summary)
            return turn.id
        except Exception as exc:
            self._degrade(exc)
            return None

    def save_state(self, state: ConversationState) -> None:
        if not self.store:
            return
        try:
            self.store.save_state(state, summary=state.conversation_summary)
        except Exception as exc:
            self._degrade(exc)

    def reset_conversation(self, conversation_id: str) -> ConversationState:
        if not self.store:
            return ConversationState(conversation_id=conversation_id)
        try:
            return self.store.reset_conversation(conversation_id)
        except Exception as exc:
            self._degrade(exc)
            return ConversationState(conversation_id=conversation_id)

    def delete_conversation(self, conversation_id: str) -> None:
        if not self.store:
            return
        try:
            self.store.delete_conversation(conversation_id)
        except Exception as exc:
            self._degrade(exc)

    def list_conversations(self) -> list[dict[str, Any]]:
        if not self.store:
            return []
        try:
            return [record.model_dump() for record in self.store.list_conversations()]
        except Exception as exc:
            self._degrade(exc)
            return []

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        if not self.store:
            return None
        try:
            record = self.store.get_conversation(conversation_id)
            return record.model_dump() if record else None
        except Exception as exc:
            self._degrade(exc)
            return None

    def update_conversation(self, conversation_id: str, *, title: str | None = None, status: str | None = None) -> None:
        if not self.store:
            return
        try:
            self.store.update_conversation(conversation_id, title=title, status=status)
        except Exception as exc:
            self._degrade(exc)

    def load_recent_turns(self, conversation_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.store:
            return []
        try:
            return self.store.load_recent_turns(conversation_id, limit or self.recent_turns_limit)
        except Exception as exc:
            self._degrade(exc)
            return []

    def load_result_reference(self, cache_id: str) -> tuple[dict[str, Any] | None, pd.DataFrame | None]:
        if not self.store:
            return None, None
        try:
            record = self.store.load_result_reference(cache_id)
            if not record:
                return None, None
            return record, self.result_cache.load_dataframe(record.get("parquet_path"))
        except Exception as exc:
            self._degrade(exc)
            return None, None

    def snapshot(self) -> dict[str, Any]:
        if not self.store:
            return {"persistence_degraded": self.persistence_degraded, "error": self.last_error}
        try:
            snap = self.store.snapshot()
            snap["persistence_degraded"] = self.persistence_degraded
            snap["error"] = self.last_error
            return snap
        except Exception as exc:
            self._degrade(exc)
            return {"persistence_degraded": True, "error": self.last_error}

    def _degrade(self, exc: Exception) -> None:
        self.persistence_degraded = True
        self.last_error = str(exc)
