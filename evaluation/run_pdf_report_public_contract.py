from __future__ import annotations

import json

from pdf_report_benchmark_utils import (
    EXPECTED_PUBLIC_SECTIONS,
    forbidden_hits,
    generate_report,
    public_payload_text,
    report_app,
    REPORT_QUESTION,
    write_artifact,
)
import src.application.chat_service as chat_service


def _model_failure_case() -> dict:
    original_chat = chat_service.OllamaClient.chat

    def failing_chat(self, messages):  # noqa: ANN001
        raise RuntimeError("model unavailable for benchmark")

    chat_service.OllamaClient.chat = failing_chat
    try:
        with report_app() as (app, record, _tmp):
            conversation = app.create_conversation("pdf-report-model-failure", source_file_id=str(record["id"]))
            response = app.process_message(conversation.id, REPORT_QUESTION, debug=True, source_file_id=str(record["id"]))
            public_response = app.public_chat_response(response)
            trace = (response.metadata or {}).get("management_commentary_trace", {})
            return {
                "response_type": response.response_type,
                "pdf_status": response.report.pdf_status if response.report else None,
                "public_forbidden_hits": forbidden_hits(public_payload_text(public_response)),
                "trace": trace,
            }
    finally:
        chat_service.OllamaClient.chat = original_chat


def run() -> dict:
    case = generate_report(debug=True)
    response = case["response"]
    public_response = case["public_response"]
    report = public_response.report
    public_text = public_payload_text(public_response)
    raw_report_text = public_payload_text(report) if report else ""
    downloads = response.downloads
    section_types = [section.section_type for section in report.sections] if report else []
    model_failure = _model_failure_case()
    trace = model_failure.get("trace") or {}
    checks = {
        "public_response_type_report": public_response.response_type == "report",
        "exactly_8_sections": section_types == EXPECTED_PUBLIC_SECTIONS,
        "single_pdf_download": len(downloads) == 1 and downloads[0].mime_type == "application/pdf",
        "no_html_xlsx_downloads": not any(item.filename.lower().endswith((".html", ".xlsx")) for item in downloads),
        "no_legacy_download_urls": "html_download_url" not in raw_report_text and "xlsx_download_url" not in raw_report_text,
        "public_payload_no_forbidden_tokens": not forbidden_hits(public_text),
        "public_metadata_safe": not any(key in public_response.metadata for key in ["execution_mode", "query_plan_id", "management_commentary_trace"]),
        "model_failure_still_generates_report": model_failure["response_type"] == "report" and model_failure["pdf_status"] == "ready",
        "model_failure_not_silent": trace.get("llm_request_started") is True and trace.get("llm_request_completed") is False and trace.get("silent_fallback") is False,
        "model_failure_public_no_forbidden_tokens": not model_failure["public_forbidden_hits"],
    }
    payload = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "section_types": section_types,
        "downloads": [item.model_dump(mode="json") for item in downloads],
        "model_failure": model_failure,
        "public_forbidden_hits": forbidden_hits(public_text),
    }
    write_artifact("pdf_report_contract_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
