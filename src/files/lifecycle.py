from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd
from fastapi import UploadFile

from src.catalog.profiler import build_catalog, load_catalog
from src.config import Settings, get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import (
    find_uploaded_file,
    list_uploaded_files,
    public_uploaded_file,
    remove_uploaded_file,
    replace_uploaded_file,
    stored_path,
    upload_dir,
)
from src.ingestion.cache_manager import ParquetCache


ALLOWED_EXTENSION = ".xlsx"
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}
READY_STATUSES = {"ready"}
PROCESSING_STATUSES = {"uploaded", "uploading", "processing"}


class FileLifecycleError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def payload(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class FileLifecycleService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.cache = ParquetCache(self.settings.cache_dir)

    def upload(self, file: UploadFile) -> dict[str, Any]:
        original_name = _sanitize_filename(file.filename or "")
        content_type = (file.content_type or "").lower()
        if not original_name.lower().endswith(ALLOWED_EXTENSION):
            raise FileLifecycleError("UNSUPPORTED_EXTENSION", "Only .xlsx files are supported")
        if content_type not in ALLOWED_MIME_TYPES:
            raise FileLifecycleError("UNSUPPORTED_MIME_TYPE", "Unsupported Excel MIME type")

        file_id = uuid4().hex
        stored_name = f"{file_id}{ALLOWED_EXTENSION}"
        uploads = upload_dir()
        uploads.mkdir(parents=True, exist_ok=True)
        destination = (uploads / stored_name).resolve()
        if destination.parent != uploads.resolve():
            raise FileLifecycleError("INVALID_UPLOAD_PATH", "Invalid upload path")

        with destination.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        sha256 = _sha256(destination)
        duplicate = next(
            (
                item
                for item in list_uploaded_files(raw=True)
                if item.get("sha256") == sha256 and item.get("status") != "deleting"
            ),
            None,
        )
        record = {
            "id": file_id,
            "filename": original_name,
            "stored_name": stored_name,
            "stored_relative_path": str(Path("data") / "uploads" / stored_name),
            "extension": ALLOWED_EXTENSION,
            "size_bytes": destination.stat().st_size,
            "sha256": sha256,
            "status": "uploaded",
            "processing_stage": "uploaded",
            "progress": 0,
            "queryable": False,
            "error": None,
            "uploaded_at": _now(),
            "duplicate_content": bool(duplicate),
            "existing_file_id": duplicate.get("id") if duplicate else None,
        }
        replace_uploaded_file(record)
        try:
            return public_uploaded_file(self.process_file(file_id))
        except FileLifecycleError:
            failed = find_uploaded_file(file_id, raw=True)
            if failed:
                return public_uploaded_file(failed)
            raise

    def process_file(self, file_id: str, *, force: bool = True) -> dict[str, Any]:
        record = find_uploaded_file(file_id, raw=True)
        if not record:
            raise FileLifecycleError("FILE_NOT_FOUND", "File not found", status_code=404)
        source_path = stored_path(record)
        try:
            self._set_status(record, "processing", "file_validation", 5)
            if source_path is None or not source_path.exists():
                raise FileLifecycleError("RAW_FILE_MISSING", "Raw uploaded file is missing")
            expected_sha = str(record.get("sha256") or "")
            current_sha = _sha256(source_path)
            if expected_sha and current_sha != expected_sha:
                raise FileLifecycleError("SHA256_MISMATCH", "Raw uploaded file checksum does not match metadata")
            if not expected_sha:
                record["sha256"] = current_sha

            self._set_status(record, "processing", "sheet_scanning", 25)
            try:
                with pd.ExcelFile(source_path):
                    pass
            except Exception as exc:
                raise FileLifecycleError("WORKBOOK_UNREADABLE", f"Could not read workbook: {exc}") from exc

            self._set_status(record, "processing", "parquet_write", 70)
            tables = self.cache.refresh_uploaded_file(
                file_id=file_id,
                source_path=source_path,
                original_filename=str(record.get("filename") or source_path.name),
                sha256=str(record.get("sha256") or current_sha),
                force=force,
            )
            if not tables:
                raise FileLifecycleError("NO_TABLES_DETECTED", "No queryable table was detected in this workbook")

            self._set_status(record, "processing", "catalog_update", 90)
            catalog = build_catalog(self.cache.load_tables(), self.settings.cache_dir)

            self._set_status(record, "processing", "query_validation", 98)
            readiness = self.validate_readiness(file_id, catalog=catalog)
            if not readiness["ok"]:
                code = str(readiness.get("code") or "READINESS_FAILED")
                raise FileLifecycleError(code, str(readiness.get("message") or "Uploaded file is not queryable"), details=readiness)

            table_summaries = [
                {
                    "table_name": table["table_name"],
                    "source_sheet": table.get("source_sheet"),
                    "row_count": int(table.get("row_count") or 0),
                    "parquet_path": table.get("parquet_path"),
                }
                for table in readiness["tables"]
            ]
            record.update(
                {
                    "status": "ready",
                    "processing_stage": "ready",
                    "progress": 100,
                    "queryable": True,
                    "error": None,
                    "ready_at": _now(),
                    "failed_at": None,
                    "sheet_count": len({table.get("source_sheet") for table in readiness["tables"]}),
                    "table_count": len(readiness["tables"]),
                    "row_count": int(sum(int(table.get("row_count") or 0) for table in readiness["tables"])),
                    "tables": table_summaries,
                    "header_rows": [
                        {
                            "table_name": table.get("table_name"),
                            "source_sheet": table.get("source_sheet"),
                            "header_row_index": table.get("profile", {}).get("header_row_index"),
                        }
                        for table in readiness["tables"]
                    ],
                    "catalog_updated": True,
                }
            )
            replace_uploaded_file(record)
            return record
        except FileLifecycleError as exc:
            record.update(
                {
                    "status": "failed",
                    "processing_stage": "failed",
                    "progress": int(record.get("progress") or 0),
                    "queryable": False,
                    "failed_at": _now(),
                    "error": exc.payload(),
                }
            )
            replace_uploaded_file(record)
            raise
        except Exception as exc:
            wrapped = FileLifecycleError("INGESTION_FAILED", f"Could not ingest workbook: {exc}")
            record.update(
                {
                    "status": "failed",
                    "processing_stage": "failed",
                    "queryable": False,
                    "failed_at": _now(),
                    "error": wrapped.payload(),
                }
            )
            replace_uploaded_file(record)
            raise wrapped from exc

    def validate_readiness(self, file_id: str, *, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
        record = find_uploaded_file(file_id, raw=True)
        if not record:
            return _not_ready("FILE_NOT_FOUND", "File metadata does not exist")
        source_path = stored_path(record)
        if source_path is None or not source_path.exists():
            return _not_ready("RAW_FILE_MISSING", "Raw uploaded file is missing")
        expected_sha = str(record.get("sha256") or "")
        if expected_sha and _sha256(source_path) != expected_sha:
            return _not_ready("SHA256_MISMATCH", "Raw uploaded file checksum does not match metadata")
        if catalog is None:
            catalog = self._load_or_build_catalog()
        catalog_tables = [
            table
            for table in catalog.get("tables", [])
            if _table_file_id(table) == file_id
        ]
        if not catalog_tables:
            return _not_ready("CATALOG_FILE_MISSING", "Catalog has no table for this uploaded file")

        checked_tables = []
        total_rows = 0
        for table in catalog_tables:
            parquet_path = _resolve_path(table.get("parquet_path"), self.settings.root)
            if parquet_path is None or not parquet_path.exists():
                return _not_ready("PARQUET_FILE_MISSING", f"Parquet cache is missing for table {table.get('table_name')}")
            try:
                with duckdb.connect(database=":memory:", read_only=False) as con:
                    row = con.execute("SELECT COUNT(*) AS c FROM read_parquet(?)", [str(parquet_path)]).fetchone()
                    count = int(row[0] if row else 0)
                    columns = set(con.execute("SELECT * FROM read_parquet(?) LIMIT 0", [str(parquet_path)]).fetchdf().columns)
                    if "_source_file_id" not in columns:
                        return _not_ready("PROVENANCE_COLUMN_MISSING", f"Missing _source_file_id in {table.get('table_name')}")
                    bad = con.execute(
                        "SELECT COUNT(*) AS c FROM read_parquet(?) WHERE _source_file_id IS NULL OR _source_file_id <> ?",
                        [str(parquet_path), file_id],
                    ).fetchone()
                    if int(bad[0] if bad else 0) > 0:
                        return _not_ready("PROVENANCE_FILE_MISMATCH", f"Provenance does not match file_id for {table.get('table_name')}")
            except Exception as exc:
                return _not_ready("DUCKDB_READ_FAILED", f"DuckDB could not read {table.get('table_name')}: {exc}")
            if count <= 0:
                return _not_ready("EMPTY_TABLE", f"Table {table.get('table_name')} has no rows")
            checked = dict(table)
            checked["row_count"] = count
            checked_tables.append(checked)
            total_rows += count

        return {"ok": True, "file_id": file_id, "table_count": len(checked_tables), "row_count": total_rows, "tables": checked_tables}

    def delete_file(self, file_id: str) -> None:
        record = find_uploaded_file(file_id, raw=True)
        if not record:
            raise FileLifecycleError("FILE_NOT_FOUND", "File not found", status_code=404)
        record["status"] = "deleting"
        record["processing_stage"] = "deleting"
        replace_uploaded_file(record)
        self.clear_active_file_references(file_id)
        self.cache.remove_file(file_id)
        build_catalog(self.cache.load_tables(), self.settings.cache_dir)
        source_path = stored_path(record)
        if source_path and source_path.exists():
            source_path.unlink()
        remove_uploaded_file(file_id)

    def reconcile_uploaded_files(self, *, auto_retry: bool = True) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for record in list_uploaded_files(raw=True):
            file_id = str(record.get("id") or "")
            if not file_id:
                continue
            status = str(record.get("status") or "")
            readiness = self.validate_readiness(file_id)
            if readiness["ok"]:
                record.update(
                    {
                        "status": "ready",
                        "processing_stage": "ready",
                        "progress": 100,
                        "queryable": True,
                        "error": None,
                        "row_count": readiness["row_count"],
                        "table_count": readiness["table_count"],
                        "sheet_count": len({table.get("source_sheet") for table in readiness["tables"]}),
                    }
                )
                replace_uploaded_file(record)
                results.append({"file_id": file_id, "action": "validated_ready", "ok": True})
                continue
            if auto_retry and status in READY_STATUSES | PROCESSING_STATUSES:
                try:
                    self.process_file(file_id, force=False)
                    results.append({"file_id": file_id, "action": "reingested", "ok": True})
                except FileLifecycleError as exc:
                    results.append({"file_id": file_id, "action": "failed", "ok": False, "error": exc.payload()})
            else:
                results.append({"file_id": file_id, "action": "left_unchanged", "ok": False, "readiness": readiness})
        return {"checked": len(results), "results": results}

    def clear_active_file_references(self, file_id: str) -> int:
        # Conversation source bindings are immutable. Deleting an uploaded file
        # must not erase historical provenance; old chats render from persisted
        # snapshots and expose the source as unavailable.
        return 0

    def _set_status(self, record: dict[str, Any], status: str, stage: str, progress: int) -> None:
        record.update({"status": status, "processing_stage": stage, "progress": progress, "queryable": False})
        if status == "processing" and not record.get("processing_started_at"):
            record["processing_started_at"] = _now()
        replace_uploaded_file(record)

    def _load_or_build_catalog(self) -> dict[str, Any]:
        catalog_path = self.settings.cache_dir / "data_catalog.json"
        if catalog_path.exists():
            try:
                return load_catalog(self.settings.cache_dir)
            except Exception:
                pass
        return build_catalog(self.cache.load_tables(), self.settings.cache_dir)


def _sanitize_filename(filename: str) -> str:
    base = Path(filename).name.strip() or "upload.xlsx"
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base)
    return base[:180] or "upload.xlsx"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_file_id(table: dict[str, Any]) -> str:
    profile = table.get("profile") if isinstance(table.get("profile"), dict) else {}
    return str(table.get("file_id") or table.get("source_file_id") or profile.get("source_file_id") or "")


def _resolve_path(value: Any, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = root / path
    return path


def _not_ready(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "message": message}
