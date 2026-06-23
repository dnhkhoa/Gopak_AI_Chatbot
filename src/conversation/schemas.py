from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = "Hoi thoai moi"
    source_file_id: str | None = None
    source_file_name: str | None = None
    source_file_sha256: str | None = None
    source_catalog_version: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    status: Literal["active", "reset", "deleted"] = "active"


class ConversationTurn(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    turn_index: int
    role: Literal["user", "assistant", "system"]
    content: str
    execution_mode: str | None = None
    query_plan_json: str | None = None
    result_summary_json: str | None = None
    response_json: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class ResultCacheRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    turn_id: str
    parquet_path: str | None = None
    row_count: int = 0
    result_schema_json: str = Field(default="{}", alias="schema_json")
    created_at: str = Field(default_factory=utc_now_iso)
