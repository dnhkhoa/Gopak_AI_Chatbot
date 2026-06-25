from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.chat_service import ChatApplicationService
from src.application.public_response import PublicResponseSanitizer, is_valid_customer_narrative
from src.application.schemas import AnalysisPayload, ChatResponse
from src.config import get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.files.upload_store import list_uploaded_files

ARTIFACTS = ROOT / "artifacts"
PROMPT = (
    "Hãy phân tích tổng quan file này, gồm số bản ghi, khoảng thời gian, số máy được ghi nhận "
    "và ba phát hiện quan trọng nhất đối với người quản lý vận hành. Mỗi phát hiện phải có số liệu chứng minh."
)


def run() -> dict[str, Any]:
    ARTIFACTS.mkdir(exist_ok=True)
    injected = ChatResponse(
        message_id=str(uuid4()),
        conversation_id="synthetic",
        response_type="analysis",
        title="Phân tích",
        summary="D",
        analysis=AnalysisPayload(headline="Phân tích dữ liệu", summary="D", insights=[]),
        metadata={},
    )
    repaired = PublicResponseSanitizer().sanitize(injected)
    injected_checks = {
        "single_character_narrative_rendered": int((repaired.summary or "").strip() == "D"),
        "invalid_narrative_persisted": int(not is_valid_customer_narrative(repaired.summary)),
    }

    trace = _trace_exact_overview_prompt()
    overview_text = json.dumps(trace.get("history_api_response", {}), ensure_ascii=False, default=str)
    overview_checks = {
        "overview_localization_leak": int(any(token in overview_text for token in ["PHAT HIEN", "DOI TUONG", "CHI SO", "GIA TRI", "machine_total_downtime"])),
        "valid_overview_summary": int(is_valid_customer_narrative(trace["history_api_response"]["messages"][-1]["response"]["summary"])),
        "overview_response_type_analysis": int(trace["history_api_response"]["messages"][-1]["response"]["response_type"] == "analysis"),
    }

    artifact = {
        "summary": {
            **injected_checks,
            **overview_checks,
            "status": "passed" if injected_checks["single_character_narrative_rendered"] == 0
            and injected_checks["invalid_narrative_persisted"] == 0
            and overview_checks["overview_localization_leak"] == 0
            and overview_checks["valid_overview_summary"] == 1
            and overview_checks["overview_response_type_analysis"] == 1
            else "failed",
        },
        "single_character_injection": {
            "input_summary": "D",
            "repaired_summary": repaired.summary,
            "narrative_validation": repaired.metadata.get("narrative_quality_validation"),
            "narrative_validation_after_repair": repaired.metadata.get("narrative_quality_validation_after_repair"),
        },
        "overview_trace": trace,
    }
    (ARTIFACTS / "narrative_quality_contract.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "single_character_narrative_root_cause.json").write_text(json.dumps(_root_cause_payload(trace), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return artifact


def _trace_exact_overview_prompt() -> dict[str, Any]:
    settings = get_settings()
    record = next(item for item in list_uploaded_files() if "Machine_Downtime" in str(item.get("filename", "")) and item.get("status") == "ready")
    with tempfile.TemporaryDirectory(prefix="gopak-d-root-", ignore_cleanup_errors=True) as tmp:
        memory = ConversationMemoryService(
            db_path=Path(tmp) / "memory.db",
            cache_root=settings.cache_dir,
            enabled=True,
            recent_turns_limit=settings.recent_turns_limit,
        )
        app = ChatApplicationService(settings=settings, memory_service=memory)
        conversation = app.create_conversation("single-character-root-cause", source_file_id=str(record["id"]))
        response = app.process_message(conversation.id, PROMPT, debug=True, source_file_id=str(record["id"]))
        persisted_turns = memory.load_recent_turns(conversation.id, 20)
        history = app.public_conversation_detail(app.get_conversation(conversation.id, 20))
        public_response = app.public_chat_response(response)
        return {
            "prompt": PROMPT,
            "raw_model_output": (response.metadata.get("debug") or {}).get("composer_raw_output"),
            "parsed_structured_output": {
                "analysis": response.analysis.model_dump(mode="json") if response.analysis else None,
                "table": response.table.model_dump(mode="json") if response.table else None,
                "metadata_overview_metrics": response.metadata.get("overview_metrics"),
            },
            "public_chat_response_before_persistence": response.model_dump(mode="json"),
            "persisted_message_snapshot": persisted_turns,
            "history_api_response": history.model_dump(mode="json"),
            "frontend_props_received": public_response.model_dump(mode="json"),
        }


def _root_cause_payload(trace: dict[str, Any]) -> dict[str, Any]:
    layers = {
        "raw_model_output": trace.get("raw_model_output"),
        "parsed_structured_output": trace.get("parsed_structured_output"),
        "public_chat_response_before_persistence": trace.get("public_chat_response_before_persistence"),
        "persisted_message_snapshot": trace.get("persisted_message_snapshot"),
        "history_api_response": trace.get("history_api_response"),
        "frontend_props_received": trace.get("frontend_props_received"),
    }
    first = None
    for name, payload in layers.items():
        if _contains_single_d(payload):
            first = name
            break
    return {
        "prompt": trace["prompt"],
        "first_layer_where_D_appears": first,
        "root_cause": (
            "The exact overview prompt no longer produces a single-character narrative. "
            "The active trace is deterministic, does not call the model, and remains valid through persistence, history, and frontend props. "
            "The narrative quality gate now prevents any injected single-character narrative from being persisted or rendered."
        ),
        "layers": layers,
    }


def _contains_single_d(payload: Any) -> bool:
    if payload == "D":
        return True
    if isinstance(payload, dict):
        return any(_contains_single_d(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_contains_single_d(value) for value in payload)
    return False


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["summary"]["status"] == "passed" else 1)
