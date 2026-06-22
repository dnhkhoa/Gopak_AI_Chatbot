from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.application.schemas import ConversationDetail, ConversationPayload


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ConversationPatchRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip()


__all__ = ["ConversationCreateRequest", "ConversationDetail", "ConversationPatchRequest", "ConversationPayload"]
