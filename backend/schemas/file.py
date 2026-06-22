from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


FileStatus = Literal["uploading", "processing", "ready", "failed"]


class UploadedFilePayload(BaseModel):
    id: str
    filename: str
    size_bytes: int
    status: FileStatus
    error: str | None = None
    uploaded_at: str | None = None
