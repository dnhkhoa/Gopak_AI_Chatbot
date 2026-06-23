from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.application.schemas import ActiveFilePayload, ConversationDetail, ConversationPayload


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    source_file_id: str | None = Field(default=None, min_length=1, max_length=128)


class ConversationPatchRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip()


class ActiveFileRequest(BaseModel):
    file_id: str = Field(min_length=1, max_length=128)


__all__ = [
    "ActiveFilePayload",
    "ActiveFileRequest",
    "ConversationCreateRequest",
    "ConversationDetail",
    "ConversationPatchRequest",
    "ConversationPayload",
]
