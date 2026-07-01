from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, status

from backend.schemas.file import UploadedFilePayload
from src.config import get_settings
from src.files.lifecycle import FileLifecycleError, FileLifecycleService
from src.files.upload_store import find_uploaded_file, list_uploaded_files


router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("", response_model=list[UploadedFilePayload])
def list_files() -> list[UploadedFilePayload]:
    return [UploadedFilePayload(**record) for record in list_uploaded_files()]


@router.post("/upload", response_model=UploadedFilePayload, status_code=status.HTTP_201_CREATED)
def upload_file(file: UploadFile) -> UploadedFilePayload:
    if not get_settings().customer_upload_enabled:
        raise HTTPException(status_code=403, detail={"code": "CUSTOMER_UPLOAD_DISABLED", "message": "Customer uploads are disabled for the production analytics bundle."})
    try:
        return UploadedFilePayload(**FileLifecycleService().upload(file))
    except FileLifecycleError as exc:
        if exc.code in {"UNSUPPORTED_EXTENSION", "UNSUPPORTED_MIME_TYPE", "INVALID_UPLOAD_PATH"}:
            raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc
        record_id = exc.details.get("file_id") if exc.details else None
        if record_id:
            record = find_uploaded_file(str(record_id))
            if record:
                return UploadedFilePayload(**record)
        raise HTTPException(status_code=422, detail=exc.payload()) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "UPLOAD_FAILED", "message": str(exc)}) from exc


@router.get("/{file_id}/status", response_model=UploadedFilePayload)
def file_status(file_id: str) -> UploadedFilePayload:
    record = find_uploaded_file(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return UploadedFilePayload(**record)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: str) -> None:
    try:
        FileLifecycleService().delete_file(file_id)
    except FileLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc
