from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ResponseType = Literal[
    "text",
    "scalar",
    "table",
    "chart",
    "dashboard",
    "clarification",
    "refusal",
    "error",
    "report",
    "data_overview",
    "schema",
    "sample_table",
    "data_quality",
]


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    debug: bool = False

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must not be empty")
        return cleaned


class TablePayload(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ChartPayload(BaseModel):
    type: Literal["bar", "horizontal_bar", "line", "pie"]
    title: str = ""
    x_key: str = ""
    y_keys: list[str] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)


class DashboardPayload(BaseModel):
    cards: list[dict[str, Any]] = Field(default_factory=list)
    table: TablePayload | None = None
    chart: ChartPayload | None = None


class SourcePayload(BaseModel):
    name: str
    rows: int | None = None


class FilterPayload(BaseModel):
    label: str
    operator: str
    value: Any = None


class DownloadPayload(BaseModel):
    id: str
    label: str
    filename: str
    mime_type: str


class ArtifactPayload(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int


class ChatResponse(BaseModel):
    message_id: str
    conversation_id: str
    response_type: ResponseType
    title: str = ""
    summary: str = ""
    primary_value: str | None = None
    secondary_value: str | None = None
    table: TablePayload | None = None
    chart: ChartPayload | None = None
    dashboard: DashboardPayload | None = None
    sources: list[SourcePayload] = Field(default_factory=list)
    filters: list[FilterPayload] = Field(default_factory=list)
    downloads: list[DownloadPayload] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationPayload(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    status: str


class ConversationMessage(BaseModel):
    id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str | None = None
    execution_mode: str | None = None


class ConversationDetail(ConversationPayload):
    messages: list[ConversationMessage] = Field(default_factory=list)


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    ollama_available: bool
    model: str
    database_available: bool
    memory_available: bool


class DataStatus(BaseModel):
    catalog_available: bool
    table_count: int
    tables: list[dict[str, Any]] = Field(default_factory=list)
