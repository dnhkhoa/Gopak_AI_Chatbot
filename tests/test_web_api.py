from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from backend.dependencies import get_chat_service
from backend.main import create_app
from src.files import lifecycle
from src.files import upload_store
from src.application.schemas import (
    ActiveFilePayload,
    ArtifactPayload,
    ChatResponse,
    ConversationDetail,
    ConversationMessage,
    ConversationPayload,
    DataStatus,
    HealthStatus,
)


class FakeService:
    def __init__(self, artifact_dir: Path):
        self.conversation = ConversationPayload(
            id="c1",
            title="Cuộc trò chuyện",
            created_at="2026-06-21T00:00:00Z",
            updated_at="2026-06-21T00:00:00Z",
            status="active",
            source_file_id="file-1",
            source_file_name="Machine_Downtime_20260203_100753.xlsx",
            source_available=True,
        )
        self.artifact_dir = artifact_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        (self.artifact_dir / "report.html").write_text("<html>ok</html>", encoding="utf-8")

    def health(self):
        return HealthStatus(status="ok", ollama_available=True, model="qwen3.5:9b", database_available=True, memory_available=True)

    def list_conversations(self):
        return [self.conversation]

    def create_conversation(self, title=None, source_file_id=None):
        return self.conversation.model_copy(
            update={
                "title": title or self.conversation.title,
                "source_file_id": source_file_id or self.conversation.source_file_id,
            }
        )

    def get_conversation(self, conversation_id, limit=200):
        if conversation_id != "c1":
            return None
        return ConversationDetail(**self.conversation.model_dump(), messages=[ConversationMessage(role="user", content="Xin chào")])

    def update_conversation(self, conversation_id, title):
        if conversation_id != "c1":
            return None
        return self.conversation.model_copy(update={"title": title})

    def delete_conversation(self, conversation_id):
        return None

    def reset_context(self, conversation_id):
        return self.get_conversation(conversation_id)

    def set_active_file(self, conversation_id, file_id):
        if conversation_id != "c1":
            return None
        if self.conversation.source_file_id and self.conversation.source_file_id != file_id:
            raise ValueError("CONVERSATION_FILE_MISMATCH")
        return ActiveFilePayload(
            conversation_id=conversation_id,
            active_file_id=file_id,
            active_file_name="Machine_Downtime_20260203_100753.xlsx",
            status="ready",
        )

    def process_message(self, conversation_id, message, debug=False, source_file_id=None):
        if source_file_id and source_file_id != self.conversation.source_file_id:
            raise ValueError("CONVERSATION_FILE_MISMATCH")
        return ChatResponse(
            message_id="m1",
            conversation_id=conversation_id,
            response_type="scalar",
            title="Tổng thời gian downtime",
            summary="Tương đương 82 ngày.",
            primary_value="1.989,56 giờ",
            metadata={"execution_mode": "DETERMINISTIC", "debug": {"enabled": debug}},
        )

    def data_status(self):
        return DataStatus(catalog_available=True, table_count=1, tables=[{"name": "Downtime máy", "row_count": 9151}])

    def reload_data(self):
        return self.data_status()

    def describe_artifact(self, artifact_id):
        path = self.resolve_artifact(artifact_id)
        if not path:
            return None
        return ArtifactPayload(id=path.name, filename=path.name, mime_type="text/html", size_bytes=path.stat().st_size)

    def resolve_artifact(self, artifact_id):
        if artifact_id != "report.html":
            return None
        return self.artifact_dir / artifact_id


def client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: FakeService(tmp_path)
    return TestClient(app)


def test_health_endpoint(tmp_path: Path) -> None:
    response = client(tmp_path).get("/api/health")
    assert response.status_code == 200
    assert response.json()["model"] == "qwen3.5:9b"


def test_conversation_crud_contract(tmp_path: Path) -> None:
    c = client(tmp_path)
    assert c.post("/api/conversations", json={"title": "Demo"}).status_code == 201
    assert c.get("/api/conversations").json()[0]["id"] == "c1"
    assert c.get("/api/conversations/c1").json()["messages"][0]["content"] == "Xin chào"
    assert c.patch("/api/conversations/c1", json={"title": "Tên mới"}).json()["title"] == "Tên mới"
    assert c.put("/api/conversations/c1/active-file", json={"file_id": "file-1"}).json()["active_file_id"] == "file-1"
    assert c.post("/api/conversations/c1/reset-context").status_code == 200
    assert c.delete("/api/conversations/c1").status_code == 204


def test_send_message_and_invalid_payload(tmp_path: Path) -> None:
    c = client(tmp_path)
    ok = c.post("/api/conversations/c1/messages", json={"message": "Tổng downtime là bao nhiêu?", "debug": True})
    assert ok.status_code == 200
    assert ok.json()["response_type"] == "scalar"
    bad = c.post("/api/conversations/c1/messages", json={"message": ""})
    assert bad.status_code == 422


def test_message_file_mismatch_is_rejected(tmp_path: Path) -> None:
    c = client(tmp_path)
    response = c.post("/api/conversations/c1/messages", json={"message": "Hello", "source_file_id": "file-2"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONVERSATION_FILE_MISMATCH"


def test_invalid_conversation(tmp_path: Path) -> None:
    response = client(tmp_path).get("/api/conversations/missing")
    assert response.status_code == 404


def test_data_status_and_reload(tmp_path: Path) -> None:
    c = client(tmp_path)
    assert c.get("/api/data/status").json()["table_count"] == 1
    assert c.post("/api/data/reload").json()["catalog_available"] is True


def test_artifact_download_safety(tmp_path: Path) -> None:
    c = client(tmp_path)
    assert c.get("/api/artifacts/report.html/download").status_code == 200
    assert c.get("/api/artifacts/..%2Fapp.py/download").status_code == 404


def test_file_upload_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(upload_store, "metadata_path", lambda: tmp_path / "uploaded_files.json")
    monkeypatch.setattr(upload_store, "upload_dir", lambda: tmp_path / "uploads")
    monkeypatch.setattr(lifecycle, "upload_dir", lambda: tmp_path / "uploads")
    c = client(tmp_path)

    assert c.get("/api/files").json() == []
    invalid = c.post(
        "/api/files/upload",
        files={"file": ("notes.txt", b"not excel", "text/plain")},
    )
    assert invalid.status_code == 400

    workbook = BytesIO()
    pd.DataFrame(
        {
            "No": [1, 2],
            "Machine": ["M01", "M02"],
            "Start": ["2026-01-01 08:00:00", "2026-01-01 09:00:00"],
            "End": ["2026-01-01 08:30:00", "2026-01-01 09:45:00"],
            "Duration": [30, 45],
        }
    ).to_excel(workbook, index=False)
    workbook.seek(0)
    uploaded = c.post(
        "/api/files/upload",
        files={
            "file": (
                "../demo.xlsx",
                workbook.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["filename"] == "demo.xlsx"
    assert payload["status"] == "ready"
    assert payload["queryable"] is True
    assert payload["row_count"] >= 1
    assert "stored_name" not in payload

    assert c.get(f"/api/files/{payload['id']}/status").json()["status"] == "ready"
    assert len(c.get("/api/files").json()) == 1
    assert c.delete(f"/api/files/{payload['id']}").status_code == 204
    assert c.get("/api/files").json() == []
