from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def run() -> dict:
    chat_message = (ROOT / "frontend" / "src" / "components" / "ChatMessage.tsx").read_text(encoding="utf-8")
    report_preview = (ROOT / "frontend" / "src" / "components" / "ReportPreview.tsx").read_text(encoding="utf-8")
    has_switch = "switch (response.response_type)" in chat_message
    has_report_case = 'case "report"' in chat_message and "<ReportPreview" in chat_message
    has_chart_case = 'case "chart"' in chat_message and "<ChartResult" in chat_message
    report_case_index = chat_message.find('case "report"')
    chart_case_index = chat_message.find('case "chart"')
    top_level_area = chat_message.split("export function ChatMessage", 1)[1].split("function ResponseBody", 1)[0]
    top_level_chart_dispatch_removed = "ChartResult" not in top_level_area
    section_attr = "data-section-type" in report_preview
    summary = {
        "report_dispatched_as_chart": int(not has_switch or not has_report_case or not has_chart_case or not top_level_chart_dispatch_removed),
        "report_case_before_chart_case": int(report_case_index != -1 and chart_case_index != -1 and report_case_index < chart_case_index),
        "report_preview_section_marker": int(section_attr),
        "status": "passed",
    }
    summary["status"] = "passed" if summary["report_dispatched_as_chart"] == 0 and summary["report_case_before_chart_case"] == 1 and summary["report_preview_section_marker"] == 1 else "failed"
    payload = {"summary": summary}
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "response_type_dispatch_benchmark.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["summary"]["status"] == "passed" else 1)
