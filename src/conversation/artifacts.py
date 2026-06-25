from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.conversation.schemas import utc_now_iso


class ArtifactType(StrEnum):
    ANALYSIS = "ANALYSIS"
    TABLE = "TABLE"
    CHART = "CHART"
    REPORT = "REPORT"
    CLARIFICATION = "CLARIFICATION"
    ERROR = "ERROR"


class ConversationArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: ArtifactType
    conversation_id: str
    turn_id: str
    source_file_id: str | None = None
    parent_artifact_id: str | None = None
    root_artifact_id: str | None = None
    revision_number: int = 1
    request_contract_id: str | None = None
    query_plan_ids: list[str] = Field(default_factory=list)
    query_result_ids: list[str] = Field(default_factory=list)
    payload_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class ActiveReportContext(BaseModel):
    report_id: str
    root_report_id: str
    revision_number: int = 1
    pdf_artifact_id: str | None = None
    payload_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_file_id: str | None = None
    updated_at: str = Field(default_factory=utc_now_iso)
