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
    try:
        return service.process_message(conversation_id, payload.message, payload.debug, source_file_id=payload.source_file_id)
    except ValueError as exc:
        if str(exc) == "CONVERSATION_FILE_MISMATCH":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONVERSATION_FILE_MISMATCH",
                    "message": "This conversation belongs to another Excel file. Start a new chat for the selected file.",
                },
            ) from exc
        raise
