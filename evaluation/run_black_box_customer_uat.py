from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    server = _ensure_server()
    try:
        files = _request("GET", "/api/files")
        ids = _file_ids(files)
        flows = [
            _uat_basic(ids),
            _uat_clarification(ids),
            _uat_topic_restoration(ids),
            _uat_file_switching(ids),
            _uat_restart(ids, server),
            _uat_delete_selected_file(ids),
        ]
        summary = {
            "total": len(flows),
            "passed": sum(1 for item in flows if item["passed"]),
            "critical_failures": sum(1 for item in flows if not item["passed"] and item.get("critical", True)),
            "accuracy": round(sum(1 for item in flows if item["passed"]) / max(1, len(flows)), 4),
        }
        (ARTIFACTS / "black_box_customer_uat.json").write_text(json.dumps({"summary": summary, "flows": flows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    finally:
        # Keep an already-running backend alive for the user's browser; only stop the one we started.
        if server and server.poll() is None:
            server.terminate()


def _ensure_server() -> subprocess.Popen | None:
    try:
        _request("GET", "/api/health", timeout=3)
        return None
    except Exception:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                _request("GET", "/api/health", timeout=2)
                return proc
            except Exception:
                time.sleep(1)
        raise RuntimeError("Backend did not become healthy on port 8000.")


def _uat_basic(ids: dict[str, str]) -> dict[str, Any]:
    conv = _new_conversation("UAT basic")
    _select_file(conv, ids["machine"])
    steps = [
        _message(conv, "noi dung cua data"),
        _message(conv, "dem so dong downtime"),
        _message(conv, "top 5 may theo tong downtime"),
        _message(conv, "ve bieu do cot top 5 may theo downtime"),
    ]
    return _flow("basic_analytics", steps, all(_type(step, {"data_overview", "scalar", "table", "chart"}) for step in steps))


def _uat_clarification(ids: dict[str, str]) -> dict[str, Any]:
    conv = _new_conversation("UAT clarification")
    _select_file(conv, ids["machine"])
    steps = [_message(conv, text) for text in ["ve bieu do tong quan", "toi quan tam phan thoi gian", "theo may"]]
    passed = steps[0]["response_type"] == "clarification" and steps[-1]["response_type"] in {"chart", "table"} and not _repeated_clarification(steps)
    return _flow("clarification", steps, passed)


def _uat_topic_restoration(ids: dict[str, str]) -> dict[str, Any]:
    conv = _new_conversation("UAT topic")
    _select_file(conv, ids["machine"])
    messages = ["top 5 may theo downtime", "chi thang gan nhat", "schema co nhung cot nao", "cot nao null", "quay lai phan top may luc nay", "them so lan dung"]
    steps = [_message(conv, item) for item in messages]
    passed = steps[0]["response_type"] == "table" and steps[4]["response_type"] in {"table", "chart"} and not _repeated_clarification(steps)
    return _flow("topic_restoration", steps, passed)


def _uat_file_switching(ids: dict[str, str]) -> dict[str, Any]:
    # One conversation = one immutable source file. Selecting another file creates a NEW
    # conversation; the old one is unchanged. Mismatched file requests are rejected (409).
    steps: list[dict[str, Any]] = []

    # Case 1 - selecting File B creates a new conversation; C1/File A is untouched.
    c1 = _new_conversation("UAT iso A")
    _select_file(c1, ids["machine"])
    c1_first = _message(c1, "top 5 may theo downtime")
    c2 = _new_conversation("UAT iso B")
    _select_file(c2, ids["loss"])
    c2_first = _message(c2, "top 5 nhom ton that theo so lan")
    c1_meta = _conversation(c1)
    c2_meta = _conversation(c2)
    case1_ok = (
        c1 != c2
        and c1_first["response_type"] == "table"
        and c2_first["response_type"] == "table"
        and str(c1_meta.get("source_file_id")) == ids["machine"]
        and str(c2_meta.get("source_file_id")) == ids["loss"]
        and c1_first["active_file_id"] == ids["machine"]
        and c2_first["active_file_id"] == ids["loss"]
    )
    steps.append({"name": "switch_creates_new_conversation", "passed": case1_ok, "c1": c1, "c2": c2, "c1_source": c1_meta.get("source_file_id"), "c2_source": c2_meta.get("source_file_id")})

    # Case 2 - reopening C1 keeps File A as the source and still answers within File A.
    c1_reopen = _message(c1, "tiep tuc bieu do top may luc nay")
    case2_ok = c1_reopen["response_type"] in {"chart", "table"} and c1_reopen["active_file_id"] == ids["machine"]
    steps.append({"name": "reopen_keeps_source", "passed": case2_ok, "active_file_id": c1_reopen["active_file_id"]})

    # Case 3 - sending File B context into C1/File A is rejected with 409, no message persisted.
    before = len(_messages(c1))
    rejected, status = _send_mismatch(c1, ids["loss"])
    after = len(_messages(c1))
    case3_ok = rejected and status == 409 and after == before
    steps.append({"name": "mismatch_rejected_409", "passed": case3_ok, "status": status, "messages_before": before, "messages_after": after})

    # Case 4 - pending clarification is isolated per conversation and restored on reopen.
    cp = _new_conversation("UAT pending A")
    _select_file(cp, ids["machine"])
    p1 = _message(cp, "ve bieu do tong quan")
    cq = _new_conversation("UAT pending B")
    _select_file(cq, ids["loss"])
    q1 = _message(cq, "top 5 nhom ton that theo so lan")
    p2 = _message(cp, "thoi gian")
    p3 = _message(cp, "theo may")
    case4_ok = (
        p1["response_type"] == "clarification"
        and q1["response_type"] != "clarification"
        and p3["response_type"] in {"chart", "table"}
    )
    steps.append({"name": "pending_clarification_isolation", "passed": case4_ok, "p1": p1["response_type"], "q1": q1["response_type"], "p3": p3["response_type"]})

    passed = all(step["passed"] for step in steps)
    return _flow("file_isolation_one_conversation_one_file", steps, passed)


def _conversation(conversation_id: str) -> dict[str, Any]:
    return _request("GET", f"/api/conversations/{conversation_id}") or {}


def _messages(conversation_id: str) -> list[dict[str, Any]]:
    detail = _request("GET", f"/api/conversations/{conversation_id}") or {}
    return detail.get("messages") or []


def _send_mismatch(conversation_id: str, file_id: str) -> tuple[bool, int | None]:
    try:
        _request("POST", f"/api/conversations/{conversation_id}/messages", {"message": "top 5 theo so lan", "debug": True, "source_file_id": file_id})
        return False, None
    except HTTPError as exc:
        return True, exc.code


def _uat_restart(ids: dict[str, str], server: subprocess.Popen | None) -> dict[str, Any]:
    conv = _new_conversation("UAT restart")
    _select_file(conv, ids["machine"])
    first = _message(conv, "top")
    # If this script did not start the backend, avoid killing the user's server in the middle of work.
    restarted = False
    if server and server.poll() is None:
        server.terminate()
        server.wait(timeout=10)
        new_server = _ensure_server()
        restarted = True
        if new_server:
            server = new_server
    second = _message(conv, "5")
    third = _message(conv, "may")
    passed = first["response_type"] == "clarification" and third["response_type"] == "table"
    return _flow("restart_pending", [first, second, third], passed, extra={"backend_restarted": restarted})


def _uat_delete_selected_file(ids: dict[str, str]) -> dict[str, Any]:
    # Non-destructive variant: verify missing active file behavior with a fake id, because deleting a real user upload
    # would alter the shared workspace state.
    conv = _new_conversation("UAT delete selected file")
    try:
        _request("PUT", f"/api/conversations/{conv}/active-file", {"file_id": "missing-file-id"})
        step = {"response_type": "unexpected_success"}
    except HTTPError as exc:
        step = {"response_type": "error", "status": exc.code}
    return _flow("delete_selected_file_guard", [step], step.get("status") in {404, 400}, extra={"non_destructive": True})


def _flow(name: str, steps: list[dict[str, Any]], passed: bool, critical: bool = True, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "critical": critical, "steps": steps, **(extra or {})}


def _file_ids(files: list[dict[str, Any]]) -> dict[str, str]:
    needles = {"machine": "Machine_Downtime", "loss": "Loss_Assignment", "entry": "EntryTransaction"}
    return {key: str(next(item for item in files if needle in str(item.get("filename", "")))["id"]) for key, needle in needles.items()}


def _new_conversation(title: str) -> str:
    return str(_request("POST", "/api/conversations", {"title": title})["id"])


def _select_file(conversation_id: str, file_id: str) -> None:
    _request("PUT", f"/api/conversations/{conversation_id}/active-file", {"file_id": file_id})


def _message(conversation_id: str, content: str) -> dict[str, Any]:
    response = _request("POST", f"/api/conversations/{conversation_id}/messages", {"message": content, "debug": True}, timeout=60)
    metadata = response.get("metadata") or {}
    debug = metadata.get("debug") if isinstance(metadata.get("debug"), dict) else {}
    return {
        "message": content,
        "response_type": response.get("response_type"),
        "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
        "sql": bool(metadata.get("generated_sql") or (debug or {}).get("sql")),
        "active_file_id": metadata.get("active_file_id"),
        "summary": response.get("summary"),
    }


def _type(step: dict[str, Any], allowed: set[str]) -> bool:
    return step.get("response_type") in allowed


def _repeated_clarification(steps: list[dict[str, Any]]) -> bool:
    last = None
    for step in steps:
        if step.get("response_type") == "clarification":
            current = step.get("summary")
            if current == last:
                return True
            last = current
        else:
            last = None
    return False


def _request(method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(BASE_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status == 204:
            return None
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
