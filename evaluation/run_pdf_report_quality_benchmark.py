from __future__ import annotations

import json

from pdf_report_benchmark_utils import generate_report, write_artifact


def run() -> dict:
    case = generate_report(debug=True)
    response = case["response"]
    report = response.report
    pdf_meta = response.metadata.get("pdf_report", {}) if response.metadata else {}
    verification = pdf_meta.get("render_verification", {}) if isinstance(pdf_meta, dict) else {}
    preview_images = pdf_meta.get("preview_images", []) if isinstance(pdf_meta, dict) else []
    checks = {
        "response_type_report": response.response_type == "report",
        "report_payload_present": report is not None,
        "pdf_ready": bool(report and report.pdf_status == "ready"),
        "pdf_artifact_exists": bool(case["pdf_path"] and case["pdf_path"].exists()),
        "single_pdf_download": len(response.downloads) == 1 and response.downloads[0].mime_type == "application/pdf",
        "no_customer_html_xlsx": not any(item.filename.lower().endswith((".html", ".xlsx")) for item in response.downloads),
        "page_count_positive": int(verification.get("page_count") or 0) > 0,
        "no_blank_pages": int(verification.get("blank_pages", -1)) == 0,
        "has_vietnamese": bool(verification.get("has_vietnamese")),
        "no_metadata_leakage_in_pdf": not verification.get("metadata_leakage"),
        "rendered_png_exists": bool(preview_images) and all(str(path).lower().endswith(".png") for path in preview_images),
        "pdf_title_detected": bool(verification.get("contains_pdf_title")),
    }
    payload = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "pdf_artifact": str(case["pdf_path"]) if case["pdf_path"] else None,
        "verification": verification,
        "preview_images": preview_images,
    }
    write_artifact("pdf_report_quality_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
