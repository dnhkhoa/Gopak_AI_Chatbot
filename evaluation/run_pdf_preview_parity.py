from __future__ import annotations

import json
from typing import Any

from pdf_report_benchmark_utils import extract_pdf_text, forbidden_hits, generate_report, normalized_text, write_artifact


def _first_row_value(section: Any) -> str:
    if not section or not section.table or not section.table.rows:
        return ""
    row = section.table.rows[0]
    if not row:
        return ""
    return str(next(iter(row.values())))


def _section(report: Any, section_type: str) -> Any:
    return next((section for section in report.sections if section.section_type == section_type), None)


def run() -> dict:
    case = generate_report(debug=True)
    response = case["response"]
    report = response.report
    pdf_path = case["pdf_path"]
    pdf_text = normalized_text(extract_pdf_text(pdf_path)) if pdf_path else ""
    top_machine = _first_row_value(_section(report, "top_may")) if report else ""
    top_cause = _first_row_value(_section(report, "top_nguyen_nhan")) if report else ""
    kpi_values = [normalized_text(f"{kpi.value} {kpi.unit or ''}").strip() for kpi in (report.kpis if report else [])]
    section_titles = [section.title for section in (report.sections if report else [])]
    checks = {
        "pdf_exists": bool(pdf_path and pdf_path.exists()),
        "title_matches": bool(report and report.title in pdf_text),
        "all_section_titles_match": all(title in pdf_text for title in section_titles),
        "all_kpis_match": all(value and value in pdf_text for value in kpi_values[:4]),
        "top_machine_matches": bool(top_machine and top_machine in pdf_text),
        "top_cause_matches": bool(top_cause and top_cause in pdf_text),
        "source_matches": bool(report and (report.source_file_name or report.source.name) in pdf_text),
        "limitations_match": bool(report and all(normalized_text(item) in pdf_text for item in report.limitations)),
        "no_forbidden_tokens_in_pdf": not forbidden_hits(pdf_text),
    }
    payload = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "pdf_artifact": str(pdf_path) if pdf_path else None,
        "kpi_values": kpi_values,
        "top_machine": top_machine,
        "top_cause": top_cause,
        "section_titles": section_titles,
        "pdf_forbidden_hits": forbidden_hits(pdf_text),
    }
    write_artifact("pdf_preview_parity_results.json", payload)
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
    raise SystemExit(0 if result["status"] == "passed" else 1)
