from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies import get_chat_service
from src.application import ChatApplicationService
from src.application.schemas import DataStatus


router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/status", response_model=DataStatus)
def data_status(service: ChatApplicationService = Depends(get_chat_service)) -> DataStatus:
    return service.data_status()


@router.post("/reload", response_model=DataStatus)
def reload_data(service: ChatApplicationService = Depends(get_chat_service)) -> DataStatus:
    return service.reload_data()
