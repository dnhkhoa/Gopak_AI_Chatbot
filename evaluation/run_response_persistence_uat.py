from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
BASE_URL = "http://127.0.0.1:8000/api"


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    health = _request_json("GET", "/health", timeout=10)
    conversations = _request_json("GET", "/conversations", timeout=30)
    files = _request_json("GET", "/files", timeout=30)
    details = [_request_json("GET", f"/conversations/{item['id']}", timeout=60) for item in conversations]

    checks: list[dict[str, Any]] = []
    live_vs_reloaded: list[dict[str, Any]] = []
    isolation: list[dict[str, Any]] = []
    failures: list[str] = []

    for detail in details:
        source_file_id = detail.get("source_file_id") or detail.get("active_file_id")
        source_file_name = detail.get("source_file_name") or detail.get("active_file_name")
        messages = detail.get("messages") or []
        assistant = [item for item in messages if item.get("role") == "assistant"]
        response_count = sum(1 for item in assistant if isinstance(item.get("response"), dict))
        source_ids = set()
        table_count = 0
        chart_count = 0
        debug_count = 0
        for item in assistant:
            response = item.get("response") if isinstance(item.get("response"), dict) else {}
            metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
            response_source = metadata.get("active_file_id")
            if response_source:
                source_ids.add(str(response_source))
            if response.get("table"):
                table_count += 1
            if response.get("chart"):
                chart_count += 1
            if isinstance(metadata.get("internal_debug_metadata"), dict):
                debug_count += 1
        if assistant and response_count != len(assistant):
            failures.append(f"{detail['id']} has assistant messages without structured response snapshots")
        if source_file_id and any(item != source_file_id for item in source_ids):
            failures.append(f"{detail['id']} has cross-file response provenance")
        checks.append(
            {
                "conversation_id": detail["id"],
                "title": detail.get("title"),
                "source_file_id": source_file_id,
                "source_file_name": source_file_name,
                "message_count": len(messages),
                "assistant_count": len(assistant),
                "structured_response_count": response_count,
                "table_response_count": table_count,
                "chart_response_count": chart_count,
                "debug_metadata_count": debug_count,
                "distinct_response_source_ids": sorted(source_ids),
                "passed": not assistant or (response_count == len(assistant) and (not source_file_id or source_ids <= {source_file_id})),
            }
        )

        reloaded = _request_json("GET", f"/conversations/{detail['id']}", timeout=60)
        before = _canonical_messages(messages)
        after = _canonical_messages(reloaded.get("messages") or [])
        live_vs_reloaded.append(
            {
                "conversation_id": detail["id"],
                "exact_payload_match": before == after,
                "message_count_before": len(before),
                "message_count_after": len(after),
            }
        )
        if before != after:
            failures.append(f"{detail['id']} structured payload changed across reload")

    mismatch = _mismatch_probe(conversations, files)
    isolation.append(mismatch)
    if not mismatch.get("passed"):
        failures.append("mismatched source request was not rejected cleanly")

    summary = {
        "health": health,
        "conversation_count": len(conversations),
        "structured_response_pass_rate": _ratio(sum(1 for item in checks if item["passed"]), len(checks)),
        "reload_exact_match_count": sum(1 for item in live_vs_reloaded if item["exact_payload_match"]),
        "mismatch_rejected": bool(mismatch.get("passed")),
        "critical_failures": failures,
        "status": "passed" if not failures else "failed",
    }
    (ARTIFACTS / "structured_response_persistence_results.json").write_text(
        json.dumps({"summary": summary, "checks": checks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACTS / "live_vs_reloaded_response_diff.json").write_text(
        json.dumps(live_vs_reloaded, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACTS / "conversation_isolation_uat.json").write_text(
        json.dumps({"summary": summary, "mismatch": mismatch, "checks": checks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(2)


def _mismatch_probe(conversations: list[dict[str, Any]], files: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = next((item for item in conversations if item.get("source_file_id")), None)
    if not candidate:
        return {"passed": True, "skipped": "No source-bound conversation found"}
    source_file_id = str(candidate.get("source_file_id"))
    other = next((item for item in files if item.get("id") != source_file_id and item.get("status") == "ready"), None)
    if not other:
        return {"passed": True, "skipped": "No different ready file found"}
    before = _request_json("GET", f"/conversations/{candidate['id']}", timeout=30)
    before_count = len(before.get("messages") or [])
    try:
        _request_json(
            "POST",
            f"/conversations/{candidate['id']}/messages",
            {"message": "mismatch probe", "source_file_id": other["id"]},
            timeout=30,
        )
        status = 200
        detail = {}
    except RuntimeError as exc:
        status = _http_status_from_error(str(exc))
        detail = {"error": str(exc)}
    after = _request_json("GET", f"/conversations/{candidate['id']}", timeout=30)
    after_count = len(after.get("messages") or [])
    return {
        "conversation_id": candidate["id"],
        "conversation_source_file_id": source_file_id,
        "attempted_source_file_id": other["id"],
        "http_status": status,
        "message_count_before": before_count,
        "message_count_after": after_count,
        "passed": status == 409 and before_count == after_count,
        "detail": detail,
    }


def _canonical_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": item.get("role"),
            "content": item.get("content"),
            "response": item.get("response"),
        }
        for item in messages
    ]


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
        raise RuntimeError(f"Backend is not reachable at {BASE_URL}") from exc


def _http_status_from_error(value: str) -> int:
    marker = "HTTP "
    if marker not in value:
        return 0
    try:
        return int(value.split(marker, 1)[1].split(" ", 1)[0])
    except Exception:
        return 0


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
