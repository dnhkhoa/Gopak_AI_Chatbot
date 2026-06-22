from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_chat_service
from backend.schemas.chat import ChatMessageRequest, ChatResponse
from src.application import ChatApplicationService


router = APIRouter(prefix="/api/conversations", tags=["chat"])


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
def send_message(
    conversation_id: str,
    payload: ChatMessageRequest,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ChatResponse:
    if not service.get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return service.process_message(conversation_id, payload.message, payload.debug)
