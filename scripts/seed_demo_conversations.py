from __future__ import annotations

import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
BASE_URL = "http://127.0.0.1:8000/api"

TARGET_FILES = {
    "entry": "EntryTransaction_20260203_164943.xlsx",
    "loss": "Loss_Assignment_20260203_100840.xlsx",
    "machine": "Machine_Downtime_20260203_100753.xlsx",
}


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    health = _request_json("GET", "/health", timeout=10)
    files = _ready_files()
    scenarios = _scenarios()
    results: list[dict[str, Any]] = []
    conversations: list[dict[str, Any]] = []

    for scenario in scenarios:
        conversation: dict[str, Any] | None = None
        conversation_id: str | None = None
        active_file_id = None
        active_file_name = None
        repeated_clarifications = 0
        previous_type = None
        file_sequence = []
        turns = []
        segment = 0

        def finish_conversation() -> None:
            if not conversation_id:
                return
            conversations.append(
                {
                    "demo_id": scenario["id"],
                    "title": conversation["title"] if conversation else scenario["title"],
                    "conversation_id": conversation_id,
                    "file_sequence": file_sequence.copy(),
                    "turn_count": len(turns),
                    "llm_call_count": sum(1 for turn in turns if turn["llm_called"]),
                    "repeated_clarifications": repeated_clarifications,
                    "status": "passed" if turns and all(turn["passed"] for turn in turns) else "failed",
                    "turns": turns.copy(),
                }
            )

        for step in scenario["steps"]:
            file_key = step.get("file")
            if file_key:
                target = files.get(file_key)
                if not target:
                    skipped_conversation_id = conversation_id or "not-created"
                    turns.append(_skipped_turn(scenario["id"], skipped_conversation_id, len(turns) + 1, step, f"Ready file not found for {file_key}"))
                    continue
                if active_file_id and active_file_id != target["id"]:
                    finish_conversation()
                    turns = []
                    file_sequence = []
                    repeated_clarifications = 0
                    previous_type = None
                    conversation = None
                    conversation_id = None
                if not conversation_id:
                    segment += 1
                    title = scenario["title"] if segment == 1 else f"{scenario['title']} - {Path(str(target['filename'])).stem}"
                    conversation = _request_json("POST", "/conversations", {"title": title, "source_file_id": target["id"]})
                    conversation_id = conversation["id"]
                active_file_id = target["id"]
                active_file_name = target["filename"]
                file_sequence.append(active_file_name)

            if not conversation_id:
                turn = _failed_turn(scenario["id"], "not-created", len(turns) + 1, step["message"], "No source file selected before message", active_file_id, active_file_name)
                turns.append(turn)
                results.append(turn)
                continue

            pending_messages = [step["message"]]
            scripted_answers = list(step.get("clarification_answers") or [])
            final_turn: dict[str, Any] | None = None
            while pending_messages:
                message = pending_messages.pop(0)
                turn, response = _send_turn(
                    scenario["id"],
                    conversation_id,
                    len(turns) + 1,
                    message,
                    active_file_id,
                    active_file_name,
                    require_chart=bool(step.get("require_chart")),
                    require_semantic=bool(step.get("require_semantic")),
                )
                if turn["response_type"] == "clarification" and previous_type == "clarification":
                    if turns and turn["assistant_response"] == turns[-1].get("assistant_response"):
                        repeated_clarifications += 1
                        turn["passed"] = False
                        turn["issues"].append("repeated clarification")
                previous_type = turn["response_type"]
                turns.append(turn)
                results.append(turn)
                final_turn = turn
                if turn["response_type"] != "clarification":
                    break
                answer = scripted_answers.pop(0) if scripted_answers else _choose_clarification_reply(response)
                if not answer:
                    break
                pending_messages.append(answer)
            if step.get("require_chart") and final_turn and final_turn["response_type"] == "clarification":
                final_turn["passed"] = False
                final_turn["issues"].append("clarification did not resolve to chart")

        finish_conversation()

    summary = _summary(results, conversations, health)
    payload = {"summary": summary, "conversations": conversations, "turns": results}
    (ARTIFACTS / "demo_conversation_seed_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "demo_conversation_seed_summary.md").write_text(_summary_markdown(summary, conversations), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["failed_turns"] > 0 or summary["cross_file_violations"] > 0 or summary["repeated_clarification_loops"] > 0:
        raise SystemExit(2)
    if summary["actual_llm_calls"] <= 0:
        raise SystemExit("No actual LLM calls were recorded.")


def _scenarios() -> list[dict[str, Any]]:
    return [
        {
            "id": "demo_01",
            "title": "01 - Data Overview",
            "steps": [
                {"file": "machine", "message": "File này chứa dữ liệu gì?"},
                {"message": "File có bao nhiêu bản ghi?"},
                {"message": "File này có những cột nào?"},
                {"message": "Có dữ liệu trống hoặc trùng không?"},
                {"message": "Cho tôi xem 5 dòng mẫu."},
            ],
        },
        {
            "id": "demo_02",
            "title": "02 - Transaction Analysis",
            "steps": [
                {"file": "entry", "message": "File giao dịch này chứa dữ liệu gì?"},
                {"message": "Tổng giá trị cân trong toàn bộ file là bao nhiêu?"},
                {"message": "Có bao nhiêu cổng khác nhau?"},
                {"message": "Cho tôi bảng số lượt ghi nhận theo từng cổng."},
                {"message": "Vẽ biểu đồ số lượt ghi nhận theo cổng.", "require_chart": True},
            ],
        },
        {
            "id": "demo_03",
            "title": "03 - Loss Classification",
            "steps": [
                {"file": "loss", "message": "File này có những nhóm tổn thất nào?"},
                {"message": "Loại tổn thất nào xuất hiện nhiều nhất?"},
                {"message": "Cho tôi top 5 tên tổn thất phổ biến nhất."},
                {"message": "Vẽ biểu đồ phân bố tổn thất theo loại.", "require_chart": True},
                {"message": "Thêm tỷ lệ phần trăm vào kết quả trước."},
            ],
        },
        {
            "id": "demo_04",
            "title": "04 - Machine Downtime",
            "steps": [
                {"file": "machine", "message": "Máy nào có tổng thời gian downtime cao nhất?"},
                {"message": "Cho tôi top 5 máy theo tổng thời gian downtime."},
                {"message": "Thêm số lần dừng và thời lượng trung bình của từng máy."},
                {"message": "Vẽ biểu đồ cột cho kết quả này.", "require_chart": True},
                {"message": "Kết quả này đang tính trong khoảng thời gian nào?"},
            ],
        },
        {
            "id": "demo_05",
            "title": "05 - Clarification Demo",
            "steps": [
                {
                    "file": "machine",
                    "message": "Vẽ biểu đồ tổng quan.",
                    "require_chart": True,
                    "clarification_answers": ["Tổng thời gian downtime.", "Theo máy.", "Chỉ lấy top 5."],
                },
            ],
        },
        {
            "id": "demo_06",
            "title": "06 - Topic Restore",
            "steps": [
                {"file": "machine", "message": "Cho tôi top 5 máy có tổng downtime cao nhất trong tháng gần nhất."},
                {"message": "File này có những cột nào?"},
                {"message": "Cột nào có nhiều giá trị trống nhất?"},
                {"message": "Quay lại phần top máy lúc nãy."},
                {"message": "Thêm số lần dừng của từng máy."},
            ],
        },
        {
            "id": "demo_07",
            "title": "07 - File Context Switching",
            "steps": [
                {"file": "machine", "message": "Top 5 máy theo tổng downtime."},
                {"file": "loss", "message": "Top 5 nhóm tổn thất theo số lần ghi nhận."},
                {"file": "entry", "message": "Tổng giá trị cân là bao nhiêu?"},
                {"file": "machine", "message": "Tiếp tục phần top máy lúc nãy và thêm thời lượng trung bình."},
            ],
        },
        {
            "id": "demo_08",
            "title": "08 - Casual User Questions",
            "steps": [
                {
                    "file": "machine",
                    "message": "Phân tích giúp tôi đi.",
                    "clarification_answers": ["Tôi muốn xem top 5 máy theo tổng thời gian downtime."],
                },
                {"message": "Kết quả trên nói lên điều gì?", "require_semantic": True},
                {"message": "Vẽ biểu đồ cột top 5 máy theo downtime.", "require_chart": True},
                {"message": "Kết quả này lấy từ file nào?"},
            ],
        },
    ]


def _ready_files() -> dict[str, dict[str, Any]]:
    records = _request_json("GET", "/files", timeout=30)
    mapped: dict[str, dict[str, Any]] = {}
    for key, filename in TARGET_FILES.items():
        match = next(
            (
                item
                for item in records
                if item.get("status") == "ready"
                and item.get("queryable")
                and filename.lower() in str(item.get("filename", "")).lower()
            ),
            None,
        )
        if match:
            mapped[key] = match
    return mapped


def _send_turn(
    demo_id: str,
    conversation_id: str,
    turn_index: int,
    message: str,
    active_file_id: str | None,
    active_file_name: str | None,
    *,
    require_chart: bool,
    require_semantic: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    try:
        response = _request_json(
            "POST",
            f"/conversations/{conversation_id}/messages",
            {"message": message, "debug": False, "source_file_id": active_file_id},
            timeout=240,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        turn = _validate_turn(
            demo_id,
            conversation_id,
            turn_index,
            message,
            response,
            active_file_id,
            active_file_name,
            require_chart=require_chart,
            require_semantic=require_semantic,
            elapsed_ms=elapsed_ms,
        )
        return turn, response
    except Exception as exc:
        return _failed_turn(demo_id, conversation_id, turn_index, message, str(exc), active_file_id, active_file_name), {}


def _choose_clarification_reply(response: dict[str, Any]) -> str | None:
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    pending = metadata.get("pending_clarification_after") if isinstance(metadata.get("pending_clarification_after"), dict) else {}
    missing = pending.get("missing_slots") if isinstance(pending.get("missing_slots"), list) else []
    slot = str(missing[0]) if missing else ""
    question = str(response.get("summary") or "").lower()
    file_name = str(metadata.get("active_file_name") or "").lower()
    is_machine = "machine_downtime" in file_name or "downtime" in file_name
    is_loss = "loss_assignment" in file_name or "tổn thất" in file_name
    is_entry = "entrytransaction" in file_name or "transaction" in file_name
    if slot == "metric":
        if "số lần" in question or "ban ghi" in question:
            return "Số lần ghi nhận."
        if is_loss:
            return "Số lần ghi nhận theo từng nhóm tổn thất."
        if is_entry:
            return "Số lượt ghi nhận theo từng cổng."
        return "Tổng thời gian downtime."
    if slot == "dimension":
        if "nguyên nhân" in question or "tổn thất" in question or is_loss:
            return "Theo nhóm tổn thất."
        if is_entry:
            return "Theo cổng."
        return "Theo máy."
    if slot == "limit":
        return "Top 5."
    if slot == "output":
        return "Biểu đồ cột."
    if "tổng thời lượng" in question or "thời gian" in question:
        if is_loss:
            return "Tổng thời gian theo nhóm tổn thất, top 5."
        return "Tổng thời gian downtime theo máy, top 5."
    return None


def _validate_turn(
    demo_id: str,
    conversation_id: str,
    turn_index: int,
    message: str,
    response: dict[str, Any],
    active_file_id: str | None,
    active_file_name: str | None,
    *,
    require_chart: bool,
    require_semantic: bool,
    elapsed_ms: float,
) -> dict[str, Any]:
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    latency = metadata.get("latency_ms") if isinstance(metadata.get("latency_ms"), dict) else {}
    issues = []
    text = json.dumps(response, ensure_ascii=False)
    response_type = str(response.get("response_type") or "")
    if not (response.get("summary") or response.get("title") or response.get("primary_value") or response.get("table") or response.get("chart")):
        issues.append("empty response")
    if active_file_id and metadata.get("active_file_id") not in {active_file_id, None}:
        issues.append("wrong active file")
    if require_chart and response_type != "clarification" and response_type != "chart" and not response.get("chart"):
        issues.append("missing chart")
    if require_semantic:
        if response_type == "clarification":
            pass
        elif response_type != "text":
            issues.append("semantic follow-up returned structured query instead of narrative")
        if response_type != "clarification" and str(metadata.get("execution_mode") or metadata.get("mode")) != "REAL_LLM":
            issues.append("semantic follow-up did not use real LLM")
    if re.search(r"[A-Za-z]:\\\\", text):
        issues.append("absolute local path shown")
    if "Traceback" in text:
        issues.append("stack trace shown")
    source_ids = []
    internal = metadata.get("internal_debug_metadata") if isinstance(metadata.get("internal_debug_metadata"), dict) else {}
    if isinstance(internal.get("source_file_ids"), list):
        source_ids = [str(item) for item in internal.get("source_file_ids")]
    if source_ids and active_file_id and any(item != active_file_id for item in source_ids):
        issues.append("cross-file source")
    return {
        "demo_id": demo_id,
        "conversation_id": conversation_id,
        "turn_index": turn_index,
        "user_message": message,
        "assistant_response": response.get("summary") or response.get("primary_value") or response.get("title") or "",
        "response_type": response_type,
        "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
        "llm_called": bool(metadata.get("llm_called")),
        "llm_model": metadata.get("llm_model"),
        "llm_latency_ms": metadata.get("llm_latency_ms") or latency.get("llm"),
        "active_file_id": metadata.get("active_file_id") or active_file_id,
        "active_file_name": metadata.get("active_file_name") or active_file_name,
        "source_file_ids": source_ids,
        "filters": response.get("filters") or [],
        "elapsed_ms": elapsed_ms,
        "passed": not issues,
        "issues": issues,
    }


def _summary(results: list[dict[str, Any]], conversations: list[dict[str, Any]], health: dict[str, Any]) -> dict[str, Any]:
    llm_latencies = [float(item["llm_latency_ms"]) for item in results if item.get("llm_latency_ms")]
    modes = Counter(str(item.get("execution_mode") or "UNKNOWN") for item in results)
    response_types = Counter(str(item.get("response_type") or "unknown") for item in results)
    return {
        "health": health,
        "demo_conversations_created": len(conversations),
        "total_turns": len(results),
        "passed_turns": sum(1 for item in results if item["passed"]),
        "failed_turns": sum(1 for item in results if not item["passed"]),
        "actual_llm_calls": sum(1 for item in results if item["llm_called"]),
        "deterministic_turns": modes.get("DETERMINISTIC", 0),
        "real_llm_turns": modes.get("REAL_LLM", 0),
        "clarification_turns": modes.get("CLARIFICATION", 0),
        "cross_file_violations": sum(1 for item in results if "cross-file source" in item["issues"] or "wrong active file" in item["issues"]),
        "repeated_clarification_loops": sum(item["repeated_clarifications"] for item in conversations),
        "response_types": dict(response_types),
        "execution_modes": dict(modes),
        "average_llm_latency_ms": round(statistics.mean(llm_latencies), 1) if llm_latencies else None,
        "p50_llm_latency_ms": round(statistics.median(llm_latencies), 1) if llm_latencies else None,
        "p95_llm_latency_ms": round(_percentile(llm_latencies, 95), 1) if llm_latencies else None,
    }


def _summary_markdown(summary: dict[str, Any], conversations: list[dict[str, Any]]) -> str:
    lines = [
        "# Demo Conversation Seed Summary",
        "",
        f"- Demo conversations created: {summary['demo_conversations_created']}",
        f"- Total turns: {summary['total_turns']}",
        f"- Passed turns: {summary['passed_turns']}",
        f"- Failed turns: {summary['failed_turns']}",
        f"- Actual LLM calls: {summary['actual_llm_calls']}",
        f"- Deterministic turns: {summary['deterministic_turns']}",
        f"- REAL_LLM turns: {summary['real_llm_turns']}",
        f"- Clarification turns: {summary['clarification_turns']}",
        f"- Cross-file violations: {summary['cross_file_violations']}",
        f"- Repeated clarification loops: {summary['repeated_clarification_loops']}",
        f"- LLM P50/P95 latency: {summary['p50_llm_latency_ms']} / {summary['p95_llm_latency_ms']} ms",
        "",
        "## Conversations",
        "",
    ]
    for item in conversations:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"- Conversation ID: `{item['conversation_id']}`",
                f"- Turns: {item['turn_count']}",
                f"- LLM calls: {item['llm_call_count']}",
                f"- Status: {item['status']}",
                f"- File sequence: {', '.join(dict.fromkeys(item['file_sequence']))}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _request_json(method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(BASE_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Backend is not reachable at {BASE_URL}. Start it with: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000") from exc


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]


def _failed_turn(demo_id: str, conversation_id: str, turn_index: int, message: str, issue: str, active_file_id: str | None, active_file_name: str | None) -> dict[str, Any]:
    return {
        "demo_id": demo_id,
        "conversation_id": conversation_id,
        "turn_index": turn_index,
        "user_message": message,
        "assistant_response": "",
        "response_type": "error",
        "execution_mode": None,
        "llm_called": False,
        "llm_model": None,
        "llm_latency_ms": None,
        "active_file_id": active_file_id,
        "active_file_name": active_file_name,
        "source_file_ids": [],
        "filters": [],
        "passed": False,
        "issues": [issue],
    }


def _skipped_turn(demo_id: str, conversation_id: str, turn_index: int, step: dict[str, Any], issue: str) -> dict[str, Any]:
    return _failed_turn(demo_id, conversation_id, turn_index, step.get("message", ""), issue, None, None)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
