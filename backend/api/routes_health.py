from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies import get_chat_service
from src.application import ChatApplicationService
from src.application.schemas import HealthStatus


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthStatus)
def health(service: ChatApplicationService = Depends(get_chat_service)) -> HealthStatus:
    return service.health()
