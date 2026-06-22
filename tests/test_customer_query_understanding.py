from __future__ import annotations

import json
from pathlib import Path

from src.application import ChatApplicationService
from src.application import chat_service
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files import upload_store


def service(tmp_path: Path, monkeypatch) -> ChatApplicationService:
    settings = get_settings()
    upload_metadata = tmp_path / "uploaded_files.json"
    upload_metadata.write_text(
        json.dumps(
            [
                {"id": "entry", "filename": "EntryTransaction_20260203_164943.xlsx", "size_bytes": 1, "status": "ready"},
                {"id": "loss", "filename": "Loss_Assignment_20260203_100840.xlsx", "size_bytes": 1, "status": "ready"},
                {
                    "id": "machine",
                    "filename": "Machine_Downtime_20260203_100753.xlsx",
                    "size_bytes": 1,
                    "status": "ready",
                    "queryable": True,
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(upload_store, "metadata_path", lambda: upload_metadata)
    monkeypatch.setattr(chat_service.FileLifecycleService, "validate_readiness", lambda self, file_id, catalog=None: {"ok": True})
    memory = ConversationMemoryService(
        db_path=tmp_path / "memory.db",
        cache_root=settings.cache_dir,
        enabled=True,
        recent_turns_limit=settings.recent_turns_limit,
    )
    return ChatApplicationService(settings=settings, memory_service=memory)


def ask(app: ChatApplicationService, question: str):
    conversation = app.create_conversation()
    app.set_active_file(conversation.id, "machine")
    return app.process_message(conversation.id, question, debug=True)


def assert_no_default_downtime(response) -> None:
    metadata = response.metadata
    sql = metadata.get("generated_sql") or (metadata.get("debug") or {}).get("sql")
    assert sql in {None, ""}
    assert response.response_type != "scalar"
    assert response.primary_value is None
    assert "1.989" not in (response.summary or "")


def test_requires_file_selection_before_data_question(tmp_path: Path, monkeypatch) -> None:
    app = service(tmp_path, monkeypatch)
    conversation = app.create_conversation()
    response = app.process_message(conversation.id, "data co gi", debug=True)
    assert response.response_type == "clarification"
    assert response.metadata["generated_sql"] is None
    assert response.metadata["file_scope_validated"] is False


def test_data_overview_does_not_default_to_downtime(tmp_path: Path, monkeypatch) -> None:
    app = service(tmp_path, monkeypatch)
    for question in ["nội dung của data", "data có gì", "có những file nào"]:
        response = ask(app, question)
        assert response.response_type == "data_overview"
        assert response.metadata["execution_mode"] == "DATA_OVERVIEW"
        assert response.metadata["active_file_id"] == "machine"
        assert response.metadata["file_scope_validated"] is True
        assert response.table is not None
        assert len(response.table.rows) >= 1
        assert_no_default_downtime(response)


def test_table_overview_does_not_run_analytical_sql(tmp_path: Path, monkeypatch) -> None:
    app = service(tmp_path, monkeypatch)
    response = ask(app, "file này chứa gì")
    assert response.response_type in {"clarification", "data_overview"}
    assert_no_default_downtime(response)


def test_schema_questions_do_not_run_sql(tmp_path: Path, monkeypatch) -> None:
    app = service(tmp_path, monkeypatch)
    for question in ["cho tôi xem schema", "có những cột nào"]:
        response = ask(app, question)
        assert response.response_type == "schema"
        assert response.table is not None
        assert response.table.rows
        assert_no_default_downtime(response)


def test_sample_rows_are_sample_table_not_scalar(tmp_path: Path, monkeypatch) -> None:
    app = service(tmp_path, monkeypatch)
    response = ask(app, "xem 5 dòng mẫu downtime")
    assert response.response_type == "sample_table"
    assert response.table is not None
    assert len(response.table.rows) <= 5
    assert_no_default_downtime(response)


def test_data_range_does_not_run_analytical_sql(tmp_path: Path, monkeypatch) -> None:
    app = service(tmp_path, monkeypatch)
    response = ask(app, "dữ liệu từ ngày nào")
    assert response.response_type == "data_overview"
    assert_no_default_downtime(response)
