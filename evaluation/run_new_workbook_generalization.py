from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from socket import timeout as SocketTimeout
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    fixtures = _create_workbooks()
    results = []
    uploaded_ids: list[str] = []
    try:
        for kind, path in fixtures:
            try:
                uploaded = _upload(path)
                uploaded_ids.append(str(uploaded["id"]))
            except (TimeoutError, SocketTimeout) as exc:
                results.append(
                    {
                        "workbook_type": kind,
                        "file": str(path),
                        "uploaded": None,
                        "selected": False,
                        "upload_error": f"UPLOAD_TIMEOUT: {exc}",
                        "passed": False,
                        "steps": [],
                    }
                )
                continue
            ready = _wait_ready(uploaded["id"])
            conv = _request_json("POST", "/api/conversations", {"title": f"Workbook generalization {kind}"})
            steps = []
            selected = False
            select_error = None
            if ready.get("status") == "ready" and ready.get("queryable"):
                try:
                    _request_json("PUT", f"/api/conversations/{conv['id']}/active-file", {"file_id": ready["id"]}, timeout=60)
                    selected = True
                except HTTPError as exc:
                    select_error = {"status": exc.code, "body": exc.read().decode("utf-8", errors="ignore")}
                except (TimeoutError, SocketTimeout) as exc:
                    select_error = {"status": "timeout", "body": str(exc)}
            if selected:
                for message in _messages_for(kind):
                    steps.append(_message(conv["id"], message))
            passed = bool(selected) and all(_acceptable(kind, step) for step in steps)
            results.append(
                {
                    "workbook_type": kind,
                    "file": str(path),
                    "uploaded": ready,
                    "selected": selected,
                    "select_error": select_error,
                    "passed": passed,
                    "steps": steps,
                }
            )
    finally:
        cleanup = _cleanup(uploaded_ids, [path for _, path in fixtures])

    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "accuracy": round(sum(1 for item in results if item["passed"]) / max(1, len(results)), 4),
        "requires_customer_workbook": True,
    }
    (ARTIFACTS / "new_workbook_generalization.json").write_text(
        json.dumps({"summary": summary, "results": results, "cleanup": cleanup}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))


def _create_workbooks() -> list[tuple[str, Path]]:
    folder = ARTIFACTS / "workbook_fixtures"
    folder.mkdir(exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    a = folder / f"Challenge_Irregular_Downtime_{suffix}.xlsx"
    b = folder / f"Challenge_Transaction_{suffix}.xlsx"
    c = folder / f"Challenge_Unseen_Schema_{suffix}.xlsx"
    downtime = pd.DataFrame(
        [
            {
                "No": 1,
                "May": "May A",
                "Thoi gian bat dau": "2026-01-01 23:30",
                "Thoi gian ket thuc": "2026-01-02 00:20",
                "Thoi luong": "00:50:00",
                "Ten ton that": "Setup",
                "Nhom ton that": "San xuat",
            },
            {
                "No": 2,
                "May": "May A",
                "Thoi gian bat dau": "2026-01-02 08:00",
                "Thoi gian ket thuc": "2026-01-02 09:15",
                "Thoi luong": "01:15:00",
                "Ten ton that": "QC",
                "Nhom ton that": "Chat luong",
            },
            {
                "No": 3,
                "May": "May B",
                "Thoi gian bat dau": "2026-01-03 10:00",
                "Thoi gian ket thuc": "2026-01-03 12:00",
                "Thoi luong": "02:00:00",
                "Ten ton that": "Vat tu",
                "Nhom ton that": "Bao tri",
            },
        ]
    )
    with pd.ExcelWriter(a) as writer:
        downtime.to_excel(writer, index=False, sheet_name="Irregular", startrow=3)
    transaction = pd.DataFrame(
        [
            {"Cong": "Gate 1", "Loai truy cap": "IN", "Thoi gian thuc thi": "2026-01-01 08:00", "Bien so xe OCR": "51A-001", "Gia tri can kg": 1200.5},
            {"Cong": "Gate 2", "Loai truy cap": "OUT", "Thoi gian thuc thi": "2026-01-01 09:30", "Bien so xe OCR": None, "Gia tri can kg": 1350.0},
        ]
    )
    transaction.to_excel(b, index=False, sheet_name="Merged Like")
    unseen = pd.DataFrame(
        [
            {"Region": "North", "Product": "A", "Units": 10, "Comment": "ok"},
            {"Region": "South", "Product": "B", "Units": 20, "Comment": None},
        ]
    )
    unseen.to_excel(c, index=False, sheet_name="Random")
    return [("irregular_downtime", a), ("transaction_report", b), ("unseen_schema", c)]


def _messages_for(kind: str) -> list[str]:
    analytical = {
        "irregular_downtime": "tong thoi gian theo may",
        "transaction_report": "dem so dong theo cong",
        "unseen_schema": "tong thoi gian theo may",
    }[kind]
    return ["noi dung cua data", "schema file nay", "xem 3 dong mau", analytical, "ve bieu do tong quan"]


def _upload(path: Path) -> dict[str, Any]:
    boundary = "----GopakBoundary" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = Request(BASE_URL + "/api/files/upload", data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_ready(file_id: str) -> dict[str, Any]:
    last = {}
    for _ in range(60):
        last = _request_json("GET", f"/api/files/{file_id}/status")
        if last.get("status") in {"ready", "failed"}:
            return last
        time.sleep(1)
    return last


def _message(conversation_id: str, message: str) -> dict[str, Any]:
    response = _request_json("POST", f"/api/conversations/{conversation_id}/messages", {"message": message, "debug": True}, timeout=60)
    metadata = response.get("metadata") or {}
    debug = metadata.get("debug") if isinstance(metadata.get("debug"), dict) else {}
    return {
        "message": message,
        "response_type": response.get("response_type"),
        "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
        "sql": bool(metadata.get("generated_sql") or (debug or {}).get("sql")),
    }


def _acceptable(kind: str, step: dict[str, Any]) -> bool:
    if step["message"] in {"noi dung cua data", "schema file nay", "xem 3 dong mau"}:
        return step["response_type"] in {"data_overview", "schema", "sample_table"}
    if kind == "unseen_schema":
        return step["response_type"] in {"clarification", "refusal", "error", "table", "scalar", "chart"}
    return step["response_type"] in {"table", "scalar", "chart", "clarification"}


def _request_json(method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(BASE_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _cleanup(uploaded_ids: list[str], fixture_paths: list[Path]) -> dict[str, Any]:
    deleted_uploads = []
    delete_errors = []
    for file_id in uploaded_ids:
        try:
            request = Request(BASE_URL + f"/api/files/{file_id}", method="DELETE")
            with urlopen(request, timeout=30):
                pass
            deleted_uploads.append(file_id)
        except Exception as exc:
            delete_errors.append({"file_id": file_id, "error": str(exc)})
    removed_fixtures = []
    for path in fixture_paths:
        try:
            path.unlink(missing_ok=True)
            removed_fixtures.append(str(path))
        except Exception as exc:
            delete_errors.append({"file": str(path), "error": str(exc)})
    return {"deleted_uploads": deleted_uploads, "removed_fixtures": removed_fixtures, "errors": delete_errors}


if __name__ == "__main__":
    main()
