from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FileStatus = Literal["uploaded", "uploading", "processing", "ready", "failed", "deleting"]


class UploadedFilePayload(BaseModel):
    id: str
    filename: str
    size_bytes: int
    status: FileStatus
    error: str | dict[str, Any] | None = None
    uploaded_at: str | None = None
    processing_stage: str | None = None
    progress: int = 0
    queryable: bool = False
    row_count: int | None = None
    sheet_count: int | None = None
    table_count: int | None = None
    ready_at: str | None = None
    failed_at: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    header_rows: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_content: bool | None = None
    existing_file_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
