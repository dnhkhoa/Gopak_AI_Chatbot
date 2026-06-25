from __future__ import annotations

from typing import Any

from src.application.schemas import ChatResponse


class ArtifactConsistencyValidator:
    """Lightweight cross-artifact validator for a single public response.

    The heavy numeric grounding validators live in ``grounding.py``. This gate
    checks the architectural invariants that prevent stale chart/table/report
    payloads from being stitched into a response from a different turn.
    """

    def validate(self, response: ChatResponse) -> dict[str, Any]:
        metadata = response.metadata or {}
        lineage = metadata.get("lineage") if isinstance(metadata.get("lineage"), dict) else {}
        checks = {
            "source": self.validate_source(response),
            "scope": self.validate_scope(response),
            "filters": self.validate_filters(response),
            "dimensions": self.validate_dimensions(response),
            "metrics": self.validate_metrics(response),
            "numeric_values": self.validate_numeric_values(response),
            "lineage": self.validate_lineage(response, lineage),
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "response_type": response.response_type,
            "lineage_keys": sorted(lineage.keys()),
        }

    def validate_source(self, response: ChatResponse) -> bool:
        if response.report is None:
            return True
        names = [response.report.source_file_name, response.report.source.name]
        if response.sources:
            names.extend(source.name for source in response.sources)
        return bool(any(str(name or "").strip() for name in names))

    def validate_scope(self, response: ChatResponse) -> bool:
        if response.report is None:
            return True
        return response.report.source_file_name == "" or response.report.source_file_name in (response.report.source.name or response.report.source_file_name)

    def validate_filters(self, response: ChatResponse) -> bool:
        return response.filters is not None

    def validate_dimensions(self, response: ChatResponse) -> bool:
        chart = response.chart
        if chart is None:
            return True
        return bool(chart.x_key and chart.data)

    def validate_metrics(self, response: ChatResponse) -> bool:
        chart = response.chart
        if chart is None:
            return True
        return bool(chart.y_keys)

    def validate_numeric_values(self, response: ChatResponse) -> bool:
        text = str(response.model_dump(mode="json"))
        return "NaN" not in text and "nan" not in text

    def validate_lineage(self, response: ChatResponse, lineage: dict[str, Any]) -> bool:
        if response.response_type in {"clarification", "error", "refusal"}:
            return True
        required = ["turn_id", "request_contract_id"]
        if response.response_type in {"table", "chart", "analysis", "scalar", "dashboard"}:
            required.append("query_result_id")
        if response.response_type == "report":
            return response.report is not None and bool(response.report.report_id)
        return all(lineage.get(key) for key in required)
