from __future__ import annotations

import json

from run_pdf_persistence_benchmark import run as run_persistence
from run_pdf_preview_parity import run as run_parity
from run_pdf_report_public_contract import run as run_contract
from run_pdf_report_quality_benchmark import run as run_quality
from state_machine_benchmark_utils import write_artifact


def run() -> dict:
    results = {
        "quality": run_quality(),
        "public_contract": run_contract(),
        "preview_parity": run_parity(),
        "persistence": run_persistence(),
    }
    payload = {
        "status": "passed" if all(item.get("status") == "passed" for item in results.values()) else "failed",
        "results": results,
    }
    write_artifact("pdf_report_benchmark_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "suite_status": {k: v.get("status") for k, v in result["results"].items()}}, ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
