from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, status

from backend.schemas.file import UploadedFilePayload
from src.config import get_settings


router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_EXTENSION = ".xlsx"
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}


@router.get("", response_model=list[UploadedFilePayload])
def list_files() -> list[UploadedFilePayload]:
    return [UploadedFilePayload(**record) for record in _load_records()]


@router.post("/upload", response_model=UploadedFilePayload, status_code=status.HTTP_201_CREATED)
def upload_file(file: UploadFile) -> UploadedFilePayload:
    original_name = _sanitize_filename(file.filename or "")
    content_type = (file.content_type or "").lower()
    if not original_name.lower().endswith(ALLOWED_EXTENSION):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported Excel MIME type")

    upload_id = uuid4().hex
    stored_name = f"{upload_id}{ALLOWED_EXTENSION}"
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = (upload_dir / stored_name).resolve()
    if destination.parent != upload_dir.resolve():
        raise HTTPException(status_code=400, detail="Invalid upload path")

    with destination.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    record = {
        "id": upload_id,
        "filename": original_name,
        "size_bytes": destination.stat().st_size,
        "status": "processing",
        "error": None,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "stored_name": stored_name,
    }
    records = _load_records(raw=True)
    records.append(record)
    _save_records(records)

    try:
        with pd.ExcelFile(destination):
            pass
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"Could not read workbook: {exc}"
    else:
        record["status"] = "ready"
        record["error"] = None
    _replace_record(record)
    return UploadedFilePayload(**record)


@router.get("/{file_id}/status", response_model=UploadedFilePayload)
def file_status(file_id: str) -> UploadedFilePayload:
    record = _find_record(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return UploadedFilePayload(**record)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: str) -> None:
    records = _load_records(raw=True)
    record = next((item for item in records if item.get("id") == file_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    stored_name = str(record.get("stored_name") or "")
    if stored_name:
        path = (_upload_dir() / stored_name).resolve()
        upload_dir = _upload_dir().resolve()
        if path.parent == upload_dir and path.exists():
            path.unlink()
    _save_records([item for item in records if item.get("id") != file_id])


def _metadata_path() -> Path:
    path = get_settings().root / "data" / "uploaded_files.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _upload_dir() -> Path:
    return get_settings().root / "data" / "uploads"


def _load_records(raw: bool = False) -> list[dict]:
    path = _metadata_path()
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(records, list):
        return []
    if raw:
        return [record for record in records if isinstance(record, dict)]
    return [_public_record(record) for record in records if isinstance(record, dict)]


def _save_records(records: list[dict]) -> None:
    path = _metadata_path()
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_record(file_id: str) -> dict | None:
    for record in _load_records(raw=True):
        if record.get("id") == file_id:
            return _public_record(record)
    return None


def _replace_record(record: dict) -> None:
    records = _load_records(raw=True)
    replaced = False
    for index, item in enumerate(records):
        if item.get("id") == record.get("id"):
            records[index] = record
            replaced = True
            break
    if not replaced:
        records.append(record)
    _save_records(records)


def _public_record(record: dict) -> dict:
    return {
        "id": str(record.get("id") or ""),
        "filename": str(record.get("filename") or ""),
        "size_bytes": int(record.get("size_bytes") or 0),
        "status": record.get("status") if record.get("status") in {"uploading", "processing", "ready", "failed"} else "failed",
        "error": record.get("error"),
        "uploaded_at": record.get("uploaded_at"),
    }


def _sanitize_filename(filename: str) -> str:
    base = Path(filename).name.strip() or "upload.xlsx"
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base)
    return base[:180] or "upload.xlsx"
