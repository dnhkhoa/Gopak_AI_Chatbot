from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.dependencies import get_chat_service
from src.application import ChatApplicationService


router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}/download")
def download_artifact(
    artifact_id: str,
    service: ChatApplicationService = Depends(get_chat_service),
) -> FileResponse:
    artifact = service.describe_artifact(artifact_id)
    path = service.resolve_artifact(artifact_id)
    if not artifact or not path:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.filename)
