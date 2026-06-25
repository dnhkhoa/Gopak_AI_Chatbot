from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ResponseType = Literal[
    "text",
    "analysis",
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
    "record_detail",
    "record_table",
    "timeline",
]


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    debug: bool = False
    source_file_id: str | None = Field(default=None, max_length=128)

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
    x_axis_unit: str | None = None
    y_axis_unit: str | None = None
    tooltip_unit: str | None = None
    source_result_id: str | None = Field(default=None, exclude=True)
    source_turn_id: str | None = Field(default=None, exclude=True)
    metric: str | None = None
    dimension: str | None = None


class DashboardPayload(BaseModel):
    cards: list[dict[str, Any]] = Field(default_factory=list)
    table: TablePayload | None = None
    chart: ChartPayload | None = None


class KpiCard(BaseModel):
    label: str
    value: str
    unit: str | None = None
    hint: str | None = None


class SourcePayload(BaseModel):
    name: str
    rows: int | None = None


class SourceInfo(BaseModel):
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


class AnalysisInsight(BaseModel):
    text: str
    evidence: list[str] = Field(default_factory=list)


class AnalysisPayload(BaseModel):
    headline: str = ""
    summary: str = ""
    insights: list[AnalysisInsight] = Field(default_factory=list)
    table: TablePayload | None = None


class PublicReportSection(BaseModel):
    section_type: str
    title: str
    summary: str | None = None
    kpis: list[KpiCard] = Field(default_factory=list)
    table: TablePayload | None = None
    chart: ChartPayload | None = None
    commentary: list[str] = Field(default_factory=list)


class ReportPayload(BaseModel):
    report_id: str
    root_report_id: str = ""
    parent_report_id: str | None = None
    revision_number: int = 1
    title: str
    report_type: str = "downtime"
    audience: str = "management"
    detail_level: str = "STANDARD"
    target_page_range: str = "2-4"
    subtitle: str | None = None
    source_file_name: str = ""
    date_range: dict[str, Any] | None = None
    generated_at: str = ""
    executive_summary: list[str] = Field(default_factory=list)
    kpis: list[KpiCard] = Field(default_factory=list)
    sections: list[PublicReportSection] = Field(default_factory=list)
    source: SourceInfo
    filters: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    pdf_status: str = "pending"
    pdf_download_url: str | None = None
    completeness: dict[str, Any] = Field(default_factory=dict)


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
    analysis: AnalysisPayload | None = None
    report: ReportPayload | None = None
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
    source_file_id: str | None = None
    source_file_name: str | None = None
    source_file_sha256: str | None = None
    source_catalog_version: str | None = None
    source_available: bool = True
    active_file_id: str | None = None
    active_file_name: str | None = None


class ConversationMessage(BaseModel):
    id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str | None = None
    execution_mode: str | None = None
    response: ChatResponse | None = None


class ConversationDetail(ConversationPayload):
    messages: list[ConversationMessage] = Field(default_factory=list)


class ActiveFilePayload(BaseModel):
    conversation_id: str
    active_file_id: str | None = None
    active_file_name: str | None = None
    status: str


ComponentHealth = Literal["HEALTHY", "DEGRADED", "UNAVAILABLE", "NOT_REQUIRED"]


class ServiceHealth(BaseModel):
    """Per-component health. A fault in one component must not make the whole
    system look down (P0-C)."""

    core_api: ComponentHealth = "HEALTHY"
    database: ComponentHealth = "HEALTHY"
    file_catalog: ComponentHealth = "HEALTHY"
    analytics_engine: ComponentHealth = "HEALTHY"
    language_model: ComponentHealth = "HEALTHY"
    report_export: ComponentHealth = "HEALTHY"


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    ollama_available: bool
    model: str
    database_available: bool
    memory_available: bool
    # Layered health (P0-C). Legacy fields above kept for backwards compatibility.
    components: ServiceHealth = Field(default_factory=ServiceHealth)
    # Only true infrastructure faults drive the customer banner; a model outage
    # or a business-level rejection must NOT flip this.
    infrastructure_degraded: bool = False
    language_model_available: bool = True
    banner_message: str | None = None
    language_model_note: str | None = None


class DataStatus(BaseModel):
    catalog_available: bool
    table_count: int
    tables: list[dict[str, Any]] = Field(default_factory=list)
