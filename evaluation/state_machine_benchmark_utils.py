from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files


ARTIFACTS = ROOT / "artifacts"


def record(name: str) -> dict[str, Any]:
    return next(item for item in list_uploaded_files() if name in str(item.get("filename", "")) and item.get("status") == "ready")


def make_app(prefix: str = "gopak-state-machine-") -> tuple[ChatApplicationService, tempfile.TemporaryDirectory]:
    settings = get_settings()
    tmp = tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True)
    memory = ConversationMemoryService(
        db_path=Path(tmp.name) / "memory.db",
        cache_root=settings.cache_dir,
        enabled=True,
        recent_turns_limit=settings.recent_turns_limit,
    )
    return ChatApplicationService(settings=settings, memory_service=memory), tmp


def write_artifact(name: str, payload: dict[str, Any]) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def ask(app: ChatApplicationService, conversation_id: str, file_id: str, message: str):
    return app.process_message(conversation_id, message, debug=True, source_file_id=file_id)
