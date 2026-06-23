from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.dependencies import get_chat_service
from backend.schemas.conversation import ActiveFilePayload, ActiveFileRequest, ConversationCreateRequest, ConversationPatchRequest
from src.application import ChatApplicationService
from src.application.schemas import ConversationDetail, ConversationPayload


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationPayload])
def list_conversations(service: ChatApplicationService = Depends(get_chat_service)) -> list[ConversationPayload]:
    return service.list_conversations()


@router.post("", response_model=ConversationPayload, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreateRequest | None = None,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ConversationPayload:
    return service.create_conversation(
        title=payload.title if payload else None,
        source_file_id=payload.source_file_id if payload else None,
    )


@router.get("/{conversation_id}", response_model=ConversationDetail, response_model_exclude_none=True)
def get_conversation(
    conversation_id: str,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ConversationDetail:
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    sanitizer = getattr(service, "public_conversation_detail", None)
    return sanitizer(conversation) if sanitizer else conversation


@router.patch("/{conversation_id}", response_model=ConversationPayload)
def update_conversation(
    conversation_id: str,
    payload: ConversationPatchRequest,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ConversationPayload:
    conversation = service.update_conversation(conversation_id, payload.title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    service: ChatApplicationService = Depends(get_chat_service),
) -> None:
    if not service.get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    service.delete_conversation(conversation_id)


@router.post("/{conversation_id}/reset-context", response_model=ConversationDetail, response_model_exclude_none=True)
def reset_context(
    conversation_id: str,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ConversationDetail:
    conversation = service.reset_context(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.put("/{conversation_id}/active-file", response_model=ActiveFilePayload)
def set_active_file(
    conversation_id: str,
    payload: ActiveFileRequest,
    service: ChatApplicationService = Depends(get_chat_service),
) -> ActiveFilePayload:
    try:
        active_file = service.set_active_file(conversation_id, payload.file_id)
    except ValueError as exc:
        message = str(exc)
        if message == "File not found":
            raise HTTPException(status_code=404, detail=message) from exc
        if message == "CONVERSATION_FILE_MISMATCH":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONVERSATION_FILE_MISMATCH",
                    "message": "This conversation belongs to another Excel file. Start a new chat for the selected file.",
                },
            ) from exc
        raise HTTPException(status_code=409, detail=message) from exc
    if not active_file:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return active_file
