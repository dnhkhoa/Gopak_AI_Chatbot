from __future__ import annotations

from functools import lru_cache

from src.application import ChatApplicationService
from src.config import get_settings


@lru_cache(maxsize=1)
def get_chat_service() -> ChatApplicationService:
    return ChatApplicationService(get_settings())
