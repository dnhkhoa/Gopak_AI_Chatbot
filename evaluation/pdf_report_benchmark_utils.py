from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files


ARTIFACTS = ROOT / "artifacts"
REPORT_QUESTION = (
    "Tạo báo cáo phân tích downtime gồm tổng downtime, tổng số lần dừng, top 5 máy, "
    "top 5 nguyên nhân, xu hướng theo thời gian, nhận xét quản lý, nguồn dữ liệu "
    "và giới hạn của kết luận."
)
EXPECTED_PUBLIC_SECTIONS = [
    "tong_quan_du_lieu",
    "tong_downtime",
    "so_lan_dung",
    "top_may",
    "top_nguyen_nhan",
    "xu_huong",
    "nhan_xet_quan_ly",
    "nguon_va_gioi_han",
]
FORBIDDEN_PUBLIC_TOKENS = [
    "SUCCESS",
    "NaN",
    "dataset_overview",
    "kpi_total_downtime",
    "management_commentary",
    "query_plan_id",
    "result_id",
    "fallback",
    "REAL_LLM",
    "execution_mode",
    "Report includes overview",
    "Sources and filters",
]


def machine_downtime_record() -> dict[str, Any]:
    return next(
        item
        for item in list_uploaded_files()
        if "Machine_Downtime" in str(item.get("filename", "")) and item.get("status") == "ready"
    )


@contextmanager
def report_app() -> Iterator[tuple[ChatApplicationService, dict[str, Any], tempfile.TemporaryDirectory]]:
    settings = get_settings()
    record = machine_downtime_record()
    tmp = tempfile.TemporaryDirectory(prefix="gopak-pdf-report-", ignore_cleanup_errors=True)
    memory = ConversationMemoryService(
        db_path=Path(tmp.name) / "memory.db",
        cache_root=settings.cache_dir,
        enabled=True,
        recent_turns_limit=settings.recent_turns_limit,
    )
    app = ChatApplicationService(settings=settings, memory_service=memory)
    try:
        yield app, record, tmp
    finally:
        tmp.cleanup()


def generate_report(debug: bool = True) -> dict[str, Any]:
    with report_app() as (app, record, _tmp):
        conversation = app.create_conversation("pdf-report-benchmark", source_file_id=str(record["id"]))
        response = app.process_message(conversation.id, REPORT_QUESTION, debug=debug, source_file_id=str(record["id"]))
        public_response = app.public_chat_response(response)
        public_history = app.public_conversation_detail(app.get_conversation(conversation.id, 20))
        pdf_path = None
        if response.downloads:
            pdf_path = app.resolve_artifact(response.downloads[0].id)
        return {
            "app": app,
            "conversation_id": conversation.id,
            "record": record,
            "response": response,
            "public_response": public_response,
            "public_history": public_history,
            "pdf_path": pdf_path,
        }


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def normalized_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").replace("\xad", "-").split())


def public_payload_text(payload: Any) -> str:
    dumped = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    return json.dumps(dumped, ensure_ascii=False, default=str)


def forbidden_hits(text: str) -> list[str]:
    return [token for token in FORBIDDEN_PUBLIC_TOKENS if token in text]


def write_artifact(name: str, payload: dict[str, Any]) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
