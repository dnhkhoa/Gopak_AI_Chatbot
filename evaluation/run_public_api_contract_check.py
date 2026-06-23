"""Check customer-facing API payloads do not expose internal routing metadata."""
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
FORBIDDEN = [
    "REAL_LLM",
    "DETERMINISTIC",
    "fallback",
    "qwen3.5",
    "llm_model",
    "execution_mode",
    "router_confidence",
    "routing_reason",
    "latency_ms",
]


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    conversations = _request_json("GET", "/conversations", timeout=30)
    details = [_request_json("GET", f"/conversations/{item['id']}", timeout=60) for item in conversations]
    checks: list[dict[str, Any]] = []
    for detail in details:
        text = json.dumps(detail, ensure_ascii=False)
        found = [term for term in FORBIDDEN if term.lower() in text.lower()]
        checks.append({
            "conversation_id": detail.get("id"),
            "message_count": len(detail.get("messages") or []),
            "forbidden_terms": found,
            "passed": not found,
        })
    summary = {
        "conversation_count": len(conversations),
        "checked_details": len(details),
        "leak_count": sum(1 for item in checks if not item["passed"]),
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
    }
    leakage_payload = {"summary": {"payload_count": len(details), "leak_count": summary["leak_count"]}, "checks": checks}
    contract_payload = {"summary": summary, "checks": checks}
    (ARTIFACTS / "internal_metadata_leakage_results.json").write_text(json.dumps(leakage_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "public_api_contract_results.json").write_text(json.dumps(contract_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "passed":
        raise SystemExit(2)


def _request_json(method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(BASE_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Backend is not reachable at {BASE_URL}") from exc


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
