from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

from src.config import get_settings

_LOCK = RLock()
FILE_STATUSES = {"uploaded", "uploading", "processing", "ready", "failed", "deleting"}


def metadata_path() -> Path:
    path = get_settings().root / "data" / "uploaded_files.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def upload_dir() -> Path:
    return get_settings().root / "data" / "uploads"


def list_uploaded_files(raw: bool = False) -> list[dict[str, Any]]:
    with _LOCK:
        path = metadata_path()
        if not path.exists():
            return []
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(records, list):
            return []
        valid = [record for record in records if isinstance(record, dict)]
        return valid if raw else [public_uploaded_file(record) for record in valid]


def save_uploaded_files(records: list[dict[str, Any]]) -> None:
    with _LOCK:
        path = metadata_path()
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp_path.replace(path)


def find_uploaded_file(file_id: str, raw: bool = False) -> dict[str, Any] | None:
    for record in list_uploaded_files(raw=True):
        if record.get("id") == file_id:
            return record if raw else public_uploaded_file(record)
    return None


def replace_uploaded_file(record: dict[str, Any]) -> dict[str, Any]:
    records = list_uploaded_files(raw=True)
    replaced = False
    for index, item in enumerate(records):
        if item.get("id") == record.get("id"):
            records[index] = record
            replaced = True
            break
    if not replaced:
        records.append(record)
    save_uploaded_files(records)
    return record


def remove_uploaded_file(file_id: str) -> dict[str, Any] | None:
    records = list_uploaded_files(raw=True)
    removed = next((record for record in records if record.get("id") == file_id), None)
    if removed:
        save_uploaded_files([record for record in records if record.get("id") != file_id])
    return removed


def stored_path(record: dict[str, Any]) -> Path | None:
    stored_name = str(record.get("stored_name") or "")
    if not stored_name:
        return None
    path = (upload_dir() / stored_name).resolve()
    uploads = upload_dir().resolve()
    if path.parent != uploads:
        return None
    return path


def public_uploaded_file(record: dict[str, Any]) -> dict[str, Any]:
    status = record.get("status") if record.get("status") in FILE_STATUSES else "failed"
    payload = {
        "id": str(record.get("id") or ""),
        "filename": str(record.get("filename") or ""),
        "size_bytes": int(record.get("size_bytes") or 0),
        "status": status,
        "error": record.get("error"),
        "uploaded_at": record.get("uploaded_at"),
        "processing_stage": record.get("processing_stage"),
        "progress": int(record.get("progress") or 0),
        "queryable": bool(record.get("queryable")) if record.get("queryable") is not None else False,
        "row_count": record.get("row_count"),
        "sheet_count": record.get("sheet_count"),
        "table_count": record.get("table_count"),
        "ready_at": record.get("ready_at"),
        "failed_at": record.get("failed_at"),
        "tables": record.get("tables") or [],
        "header_rows": record.get("header_rows") or [],
        "duplicate_content": record.get("duplicate_content"),
        "existing_file_id": record.get("existing_file_id"),
    }
    if isinstance(payload["error"], dict):
        payload["error_code"] = payload["error"].get("code")
        payload["error_message"] = payload["error"].get("message")
    return payload


def public_uploaded_file_legacy(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record.get("id") or ""),
        "filename": str(record.get("filename") or ""),
        "size_bytes": int(record.get("size_bytes") or 0),
        "status": record.get("status") if record.get("status") in FILE_STATUSES else "failed",
        "error": record.get("error"),
        "uploaded_at": record.get("uploaded_at"),
    }
