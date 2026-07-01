from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.application.schemas import (
    AnalysisInsight,
    AnalysisPayload,
    ChartPayload,
    ChatResponse,
    DownloadPayload,
    FilterPayload,
    KpiCard,
    PublicReportSection,
    ReportPayload,
    SourceInfo,
    SourcePayload,
    TablePayload,
)
from src.config import Settings
from src.conversation.artifacts import ReportArtifact, ReportScope, VerifiedFact
from src.llm.ollama_client import OllamaClient
from src.production.schemas import EvidencePack, ExecutionPlan
from src.rendering.pdf_report import export_public_report_pdf, generated_at_vn
from src.sources.registry import ProductionSource, SourceRegistry
from src.sources.routing import SourceRoute, SourceRouter, normalize_text


@dataclass(frozen=True)
class TimeWindow:
    start: datetime | None
    end: datetime | None
    label: str
    resolution: str


class ProductionAnalyticsService:
    def __init__(self, settings: Settings, registry: SourceRegistry | None = None) -> None:
        self.settings = settings
        self.registry = registry or SourceRegistry(settings)

    def process(self, conversation_id: str, question: str, context: dict | None = None) -> ChatResponse:
        sources = self.registry.load()
        orchestrated = self._orchestrated_response(conversation_id, question, sources, context or {})
        if orchestrated is not None:
            return orchestrated
        special = self._special_response(conversation_id, question, sources)
        if special is not None:
            return self._finalize_response(special, self._base_trace(conversation_id, question, "NEW_REQUEST", "METADATA", [str(item.name) for item in special.sources]))
        route = SourceRouter(sources).route(question, context)
        if route.status == "clarification":
            response = self._terminal_response(conversation_id, route, "clarification", "Clarification required", route.clarification_question or "Please clarify the metric.")
            return self._finalize_response(response, self._base_trace(conversation_id, question, "NEW_REQUEST", "CLARIFICATION", []))
        if route.status == "not_answerable":
            response = self._terminal_response(conversation_id, route, "error", "Source unavailable", route.clarification_question or "A required source is unavailable.")
            return self._finalize_response(response, self._base_trace(conversation_id, question, "NEW_REQUEST", "NOT_ANSWERABLE", []))

        source_map = {source.source_id: source for source in sources}
        timezone_error = self._timezone_error(question, route)
        if timezone_error:
            return self._terminal_response(conversation_id, route, "error", "Business timezone is required", timezone_error, state="SAFE_FAILURE")

        rows: list[dict[str, Any]] = []
        notes: list[str] = []
        plans: list[ExecutionPlan] = []
        try:
            for source_id in route.source_ids:
                source = source_map[source_id]
                plan = self._plan_for_source(question, route, source)
                plans.append(plan)
                result_rows, result_notes = self._execute_plan(source, plan)
                rows.extend(result_rows)
                notes.extend(result_notes)
        except UnsupportedCalculation as exc:
            return self._terminal_response(conversation_id, route, "refusal", "Calculation is not enabled", str(exc), state="PLAN_REJECTED")
        except Exception as exc:
            return self._terminal_response(conversation_id, route, "error", "Execution failed", str(exc), state="EXECUTION_FAILED")

        evidence = EvidencePack(
            status="ok",
            state="COMPLETED",
            sources_used=list(route.source_ids),
            time_scope=self._combined_time_scope(rows, plans),
            metric_scope=list(route.requested_metrics),
            data_version={source.source_id: {"checksum": source.checksum, "schema_fingerprint": source.schema_fingerprint} for source in sources},
            rows=rows,
            notes=notes,
            route=route.to_dict(),
            execution_plans=[plan.model_dump() for plan in plans],
        )
        response = self._render_response(conversation_id, evidence, source_map)
        return self._finalize_response(response, self._base_trace(conversation_id, question, "NEW_REQUEST", "DETERMINISTIC_ANALYTICS", list(route.source_ids)))

    def _orchestrated_response(self, conversation_id: str, question: str, sources: list[ProductionSource], context: dict) -> ChatResponse | None:
        text = normalize_text(question)
        source_map = {source.source_id: source for source in sources}
        artifacts = self._state_artifacts(context)
        latest_chart = self._latest_payload(artifacts, "DAILY_DOWNTIME_CHART")
        latest_report = self._latest_payload(artifacts, "REPORT_ARTIFACT")
        latest_apqoee = self._latest_payload(artifacts, "APQOEE_SNAPSHOT")
        latest_top_machines = self._latest_payload(artifacts, "DOWNTIME_DRILLDOWN")
        trace = self._base_trace(conversation_id, question, "NEW_REQUEST", "UNRESOLVED", [])

        try:
            report_intent = self._classify_report_intent(text, latest_report is not None)
            if report_intent == "REPORT_QUERY":
                response = self._report_query(conversation_id, latest_report, trace)
                return self._finalize_response(response, trace)
            if report_intent == "REPORT_EXPORT":
                response = self._report_export(conversation_id, latest_report, trace)
                return self._finalize_response(response, trace)
            if report_intent in {"REPORT_REVISE", "REPORT_REVISE_EXPORT"}:
                response = self._report_revision(conversation_id, question, latest_report, latest_top_machines, trace, export_after=report_intent == "REPORT_REVISE_EXPORT")
                return self._finalize_response(response, trace)
            if report_intent in {"REPORT_CREATE", "REPORT_REGENERATE"}:
                response = self._report_create(conversation_id, question, artifacts, latest_chart, latest_apqoee, trace)
                return self._finalize_response(response, trace)
            if self._is_chart_request(text):
                response = self._daily_downtime_chart(conversation_id, question, source_map["machine_downtime"], trace)
                return self._finalize_response(response, trace)
            if self._is_highest_day_drilldown(text):
                response = self._top_machines_for_chart_day(conversation_id, question, source_map["machine_downtime"], latest_chart, trace)
                return self._finalize_response(response, trace)
            if self._is_two_source_day_compare(text):
                response = self._compare_downtime_loss_for_context_day(
                    conversation_id,
                    question,
                    source_map["machine_downtime"],
                    source_map["loss_assignment"],
                    latest_chart,
                    trace,
                )
                return self._finalize_response(response, trace)
            if self._is_three_source_day_summary(text):
                response = self._three_source_day_summary(
                    conversation_id,
                    question,
                    source_map["machine_downtime"],
                    source_map["loss_assignment"],
                    source_map["apqoee_cumulative"],
                    latest_chart,
                    trace,
                )
                return self._finalize_response(response, trace)
            if self._is_apqoee_followup(text, latest_apqoee):
                response = self._apqoee_comparison_followup(conversation_id, question, source_map["apqoee_cumulative"], latest_apqoee, trace)
                return self._finalize_response(response, trace)
            if self._is_apqoee_snapshot_request(text):
                response = self._apqoee_snapshot_response(conversation_id, question, source_map["apqoee_cumulative"], trace)
                return self._finalize_response(response, trace)
        except UnsupportedCalculation as exc:
            response = self._terminal_response(
                conversation_id,
                SourceRoute(
                    status="answerable",
                    source_ids=("apqoee_cumulative",),
                    source_roles={"apqoee_cumulative": "primary"},
                    execution_strategy="single_source",
                    requested_metrics=("period_oee",),
                    requested_grain="day",
                    time_semantics="period",
                    confidence=1.0,
                ),
                "refusal",
                "Calculation is not enabled",
                str(exc),
                state="PLAN_REJECTED",
            )
            trace["resolved_intent"] = "REFUSAL"
            trace["fallback_reason"] = str(exc)
            return self._finalize_response(response, trace)
        return None

    def _base_trace(self, conversation_id: str, question: str, relationship: str, intent: str, sources: list[str]) -> dict[str, Any]:
        return {
            "turn_id": str(uuid4()),
            "conversation_id": conversation_id,
            "raw_message": question,
            "turn_relationship": relationship,
            "resolved_intent": intent,
            "referenced_artifact_id": None,
            "selected_sources": sources,
            "resolved_time_range": None,
            "response_type": None,
            "llm_called": False,
            "llm_purpose": None,
            "fallback_used": False,
            "fallback_reason": None,
            "artifact_created": None,
        }

    def _finalize_response(self, response: ChatResponse, trace: dict[str, Any]) -> ChatResponse:
        trace["response_type"] = response.response_type
        response.metadata.setdefault("sources_used", list(trace.get("selected_sources") or []))
        response.metadata.setdefault("time_scope", trace.get("resolved_time_range") or {})
        response.metadata.setdefault("metric_scope", [])
        response.metadata["production_turn_trace"] = trace
        response.metadata.setdefault("lineage", {})["turn_id"] = trace["turn_id"]
        response.metadata["llm_called"] = bool(trace.get("llm_called"))
        response.metadata["llm_purpose"] = trace.get("llm_purpose")
        response.metadata["artifact_created"] = trace.get("artifact_created")
        self._write_trace(trace)
        return response

    def _write_trace(self, trace: dict[str, Any]) -> None:
        try:
            path = self.settings.root / "logs" / "production-turn-trace.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
        except Exception:
            return

    def _state_artifacts(self, context: dict) -> list[dict[str, Any]]:
        state = context.get("state")
        artifacts = getattr(state, "artifacts", []) if state is not None else []
        out: list[dict[str, Any]] = []
        for artifact in artifacts or []:
            payload = getattr(artifact, "payload_snapshot", None) or {}
            if isinstance(payload, dict):
                out.append({"artifact_id": getattr(artifact, "artifact_id", ""), "payload": payload})
        return out

    def _latest_payload(self, artifacts: list[dict[str, Any]], artifact_type: str) -> dict[str, Any] | None:
        for item in reversed(artifacts):
            payload = item.get("payload") or {}
            created = _artifact_created_from_payload(payload)
            if isinstance(created, dict) and created.get("artifact_type") == artifact_type:
                return {"artifact_id": item.get("artifact_id"), **created, "response_payload": payload}
            if payload.get("artifact_type") == artifact_type:
                return {"artifact_id": item.get("artifact_id"), **payload}
            if artifact_type == "REPORT_ARTIFACT" and payload.get("report_id"):
                return {
                    "artifact_id": item.get("artifact_id"),
                    "artifact_type": "REPORT_ARTIFACT",
                    "report_id": payload.get("report_id"),
                    "parent_report_id": payload.get("parent_report_id"),
                    "revision_number": payload.get("revision_number"),
                    "pdf_status": payload.get("pdf_status"),
                    "response_payload": {"report": payload},
                }
        return None

    def _is_apqoee_snapshot_request(self, text: str) -> bool:
        return ("oee" in text or "apqoee" in text) and ("tich luy" in text or "den" in text or "as of" in text) and not self._is_period_specific_oee(text)

    def _is_apqoee_followup(self, text: str, latest_apqoee: dict[str, Any] | None) -> bool:
        return latest_apqoee is not None and ("oee" in text or "apqoee" in text or "con den" in text or "so sanh" in text) and self._explicit_date_from_text(text) is not None

    def _is_chart_request(self, text: str) -> bool:
        return "downtime" in text and any(term in text for term in ["bieu do", "chart", "ve "])

    def _is_highest_day_drilldown(self, text: str) -> bool:
        return ("cao nhat" in text or "vua tim" in text or "ngay do" in text) and any(term in text for term in ["top", "may", "chi tiet", "drill"])

    def _is_two_source_day_compare(self, text: str) -> bool:
        return "downtime" in text and any(term in text for term in ["ton that", "loss", "nhom"]) and any(term in text for term in ["so sanh", "ngay do", "trong ngay"])

    def _is_three_source_day_summary(self, text: str) -> bool:
        return ("tong hop" in text or "tinh hinh" in text or "nhan xet quan ly" in text) and "downtime" in text and ("oee" in text or "apqoee" in text) and any(term in text for term in ["ton that", "loss", "nhom"])

    def _classify_report_intent(self, text: str, has_report: bool) -> str | None:
        mentions_report = "bao cao" in text or has_report
        export = (
            "pdf" in text
            or "download" in text
            or "tai bao cao" in text
            or "tai file" in text
            or "xuat phien ban" in text
            or "xuat lai" in text
        )
        revise = any(
            term in text
            for term in [
                "viet phan",
                "nhan xet",
                "chi tiet",
                "them phan",
                "them bang",
                "doi tieu de",
                "rut gon",
                "phong cach",
                "bo phan",
                "gioi han",
                "chinh",
                "sua",
            ]
        )
        source_query = mentions_report and any(term in text for term in ["nguon du lieu", "nguon nao", "su dung nhung nguon", "dang su dung"])
        if source_query and not any(term in text for term in ["them", "bo", "xuat"]):
            return "REPORT_QUERY"
        if export and revise:
            return "REPORT_REVISE_EXPORT"
        if export and mentions_report:
            return "REPORT_EXPORT"
        if has_report and revise:
            return "REPORT_REVISE"
        if "bao cao" in text and any(term in text for term in ["tao", "lap", "viet", "generate", "regenerate", "lam"]):
            return "REPORT_REGENERATE" if "regenerate" in text or "tao lai" in text else "REPORT_CREATE"
        return None

    def _apqoee_snapshot_response(self, conversation_id: str, question: str, source: ProductionSource, trace: dict[str, Any]) -> ChatResponse:
        target = self._explicit_date_from_text(normalize_text(question)) or self._latest_apqoee_date(source)
        rows = self._apqoee_snapshot_rows(source, target)
        artifact = {
            "artifact_type": "APQOEE_SNAPSHOT",
            "source": "APQOEE_CUMULATIVE",
            "as_of_date": target.isoformat(),
            "metrics": ["OEE", "Availability", "Performance", "Quality"],
        }
        trace.update(
            {
                "resolved_intent": "APQOEE_SNAPSHOT",
                "selected_sources": ["apqoee_cumulative"],
                "resolved_time_range": {"as_of_date": target.isoformat()},
                "artifact_created": artifact,
            }
        )
        table = TablePayload(columns=["source_id", "source", "metric", "value", "unit", "time_scope", "snapshot_time"], rows=rows)
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="table",
            title="APQOEE Cumulative",
            summary="Các chỉ số APQOEE cumulative/tích lũy đã được tính đến snapshot được chọn.",
            table=table,
            sources=[SourcePayload(name=source.display_name)],
            filters=[FilterPayload(label="Date range", operator="as_of", value=target.isoformat())],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _apqoee_comparison_followup(self, conversation_id: str, question: str, source: ProductionSource, prior: dict[str, Any], trace: dict[str, Any]) -> ChatResponse:
        target = self._explicit_date_from_text(normalize_text(question))
        if target is None:
            return self._context_missing_response(conversation_id, "Không xác định được ngày cần so sánh từ câu hỏi.")
        baseline = date.fromisoformat(str(prior.get("as_of_date")))
        current_rows = self._apqoee_snapshot_rows(source, target)
        base_rows = self._apqoee_snapshot_rows(source, baseline)
        rows = []
        by_metric = {row["metric"]: row for row in base_rows}
        comparison_metrics = {
            "Cumulative OEE": "OEE",
            "Cumulative Availability": "Availability",
            "Cumulative Performance": "Performance",
            "Cumulative Quality": "Quality",
        }
        for row in current_rows:
            previous = by_metric.get(row["metric"], {}).get("value")
            delta = round(float(row["value"]) - float(previous), 2) if previous is not None else None
            rows.append(
                {
                    "metric": comparison_metrics.get(str(row["metric"]), str(row["metric"])),
                    "baseline_date": baseline.isoformat(),
                    "baseline_value": previous,
                    "current_date": target.isoformat(),
                    "current_value": row["value"],
                    "delta_percentage_points": delta,
                    "unit": "%",
                }
            )
        artifact = {
            "artifact_type": "APQOEE_SNAPSHOT",
            "source": "APQOEE_CUMULATIVE",
            "as_of_date": target.isoformat(),
            "baseline_date": baseline.isoformat(),
            "metrics": ["OEE", "Availability", "Performance", "Quality"],
        }
        trace.update(
            {
                "turn_relationship": "FOLLOW_UP_QUESTION",
                "resolved_intent": "APQOEE_COMPARISON",
                "referenced_artifact_id": prior.get("artifact_id"),
                "selected_sources": ["apqoee_cumulative"],
                "resolved_time_range": {"baseline": baseline.isoformat(), "current": target.isoformat()},
                "artifact_created": artifact,
            }
        )
        table = TablePayload(columns=list(rows[0].keys()), rows=rows)
        summary = f"So sánh APQOEE tích lũy đến {self._date_vi(target)} với mốc {self._date_vi(baseline)}."
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="table",
            title="So sánh APQOEE tích lũy",
            summary=summary,
            table=table,
            sources=[SourcePayload(name=source.display_name)],
            filters=[FilterPayload(label="Date range", operator="compare", value=f"{baseline.isoformat()} to {target.isoformat()}")],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _daily_downtime_chart(self, conversation_id: str, question: str, source: ProductionSource, trace: dict[str, Any]) -> ChatResponse:
        start_date, end_date = self._date_range_from_text(question)
        rows = self._daily_event_rows(source, start_date, end_date)
        if not rows:
            return self._context_missing_response(conversation_id, f"Không có dữ liệu downtime trong khoảng {self._date_vi(start_date)} đến {self._date_vi(end_date)}.")
        highest = max(rows, key=lambda row: float(row["downtime_hours"]))
        chart = ChartPayload(
            type="line",
            title="Tổng downtime theo ngày",
            x_key="date_label",
            y_keys=["downtime_hours"],
            y_axis_unit="giờ",
            tooltip_unit="giờ",
            data=rows,
        )
        insight_text, llm = self._grounded_commentary(
            "chart_insights",
            {
                "time_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "highest_date": highest["date"],
                "highest_value_hours": highest["downtime_hours"],
                "daily_rows": rows,
            },
        )
        artifact = {
            "artifact_type": "DAILY_DOWNTIME_CHART",
            "source": "MACHINE_DOWNTIME",
            "time_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "highest_date": highest["date"],
            "highest_value": highest["downtime_hours"],
            "query_result_id": str(uuid4()),
        }
        trace.update(
            {
                "resolved_intent": "DAILY_DOWNTIME_CHART",
                "selected_sources": ["machine_downtime"],
                "resolved_time_range": artifact["time_range"],
                "llm_called": llm,
                "llm_purpose": "chart_insights" if llm else None,
                "artifact_created": artifact,
            }
        )
        table = TablePayload(columns=["date_label", "downtime_hours", "event_count"], rows=rows)
        summary = (
            f"Downtime cao nhất trong khoảng là ngày {self._date_vi(date.fromisoformat(highest['date']))}: "
            f"{self._num_vi(highest['downtime_hours'])} giờ.\n\n{insight_text}"
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="chart",
            title="Biểu đồ downtime theo ngày",
            summary=summary,
            chart=chart,
            table=table,
            analysis=AnalysisPayload(headline="Nhận xét downtime theo ngày", summary=insight_text, insights=[AnalysisInsight(text=part.strip("- ").strip()) for part in insight_text.splitlines() if part.strip()]),
            sources=[SourcePayload(name=source.display_name)],
            filters=[FilterPayload(label="Date range", operator="between", value=f"{start_date.isoformat()} to {end_date.isoformat()}")],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False, "lineage": {"chart_spec_id": artifact["query_result_id"]}},
        )

    def _top_machines_for_chart_day(self, conversation_id: str, question: str, source: ProductionSource, chart_artifact: dict[str, Any] | None, trace: dict[str, Any]) -> ChatResponse:
        if not chart_artifact or not chart_artifact.get("highest_date"):
            return self._context_missing_response(conversation_id, "Chưa có biểu đồ downtime trước đó để xác định ngày downtime cao nhất.")
        target = date.fromisoformat(str(chart_artifact["highest_date"]))
        rows = self._top_machines_for_day(source, target, 5)
        trace.update(
            {
                "turn_relationship": "FOLLOW_UP_QUESTION",
                "resolved_intent": "DOWNTIME_TOP_MACHINES",
                "referenced_artifact_id": chart_artifact.get("artifact_id"),
                "selected_sources": ["machine_downtime"],
                "resolved_time_range": {"date": target.isoformat()},
                "artifact_created": {"artifact_type": "DOWNTIME_DRILLDOWN", "date": target.isoformat()},
            }
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="table",
            title="Top máy downtime trong ngày cao nhất",
            summary=f"Chi tiết top 5 máy downtime trong ngày {self._date_vi(target)}.",
            table=TablePayload(columns=list(rows[0].keys()) if rows else [], rows=rows),
            sources=[SourcePayload(name=source.display_name)],
            filters=[FilterPayload(label="Date range", operator="equals", value=target.isoformat())],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _compare_downtime_loss_for_context_day(self, conversation_id: str, question: str, downtime_source: ProductionSource, loss_source: ProductionSource, chart_artifact: dict[str, Any] | None, trace: dict[str, Any]) -> ChatResponse:
        target = self._context_day(chart_artifact)
        if target is None:
            return self._context_missing_response(conversation_id, "Chưa có ngày tham chiếu từ biểu đồ downtime trước đó.")
        downtime = self._event_totals_for_day(downtime_source, target)
        loss_groups = self._loss_groups_for_day(loss_source, target, 5)
        commentary, llm = self._grounded_commentary("multi_source_commentary", {"date": target.isoformat(), "downtime": downtime, "loss_groups": loss_groups})
        rows = [{"metric": "Tổng downtime trong ngày", "value": downtime["duration_hours"], "unit": "hours"}] + loss_groups
        trace.update(
            {
                "turn_relationship": "FOLLOW_UP_QUESTION",
                "resolved_intent": "DOWNTIME_LOSS_COMPARISON",
                "referenced_artifact_id": chart_artifact.get("artifact_id") if chart_artifact else None,
                "selected_sources": ["machine_downtime", "loss_assignment"],
                "resolved_time_range": {"date": target.isoformat()},
                "llm_called": llm,
                "llm_purpose": "multi_source_commentary" if llm else None,
                "artifact_created": {"artifact_type": "MULTI_SOURCE_DAY_COMPARISON", "date": target.isoformat()},
            }
        )
        summary = (
            f"Ngày phân tích: {self._date_vi(target)}.\n\n"
            f"Tổng downtime trong ngày: {self._num_vi(downtime['duration_hours'])} giờ.\n\n"
            "Metric xếp hạng nhóm tổn thất: tổng thời lượng tổn thất trong ngày.\n\n"
            f"{commentary}\n\n"
            "Giới hạn: kết quả cho thấy tương quan theo thời gian, không khẳng định quan hệ nhân quả trực tiếp."
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="analysis",
            title="So sánh downtime và nhóm tổn thất",
            summary=summary,
            table=TablePayload(columns=list(rows[0].keys()) if rows else [], rows=rows),
            analysis=AnalysisPayload(headline="So sánh hai nguồn dữ liệu", summary=commentary, table=TablePayload(columns=list(rows[0].keys()) if rows else [], rows=rows)),
            sources=[SourcePayload(name=downtime_source.display_name), SourcePayload(name=loss_source.display_name)],
            filters=[FilterPayload(label="Date range", operator="equals", value=target.isoformat())],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _three_source_day_summary(self, conversation_id: str, question: str, downtime_source: ProductionSource, loss_source: ProductionSource, apqoee_source: ProductionSource, chart_artifact: dict[str, Any] | None, trace: dict[str, Any]) -> ChatResponse:
        target = self._context_day(chart_artifact)
        if target is None:
            return self._context_missing_response(conversation_id, "Chưa có ngày tham chiếu từ kết quả trước để tổng hợp ba nguồn.")
        downtime = self._event_totals_for_day(downtime_source, target)
        loss_groups = self._loss_groups_for_day(loss_source, target, 3)
        apqoee_rows = self._apqoee_snapshot_rows(apqoee_source, target)
        oee = next((row for row in apqoee_rows if row["metric"] == "Cumulative OEE"), None)
        commentary, llm = self._grounded_commentary("management_commentary", {"date": target.isoformat(), "downtime": downtime, "loss_groups": loss_groups, "apqoee": apqoee_rows})
        rows = [
            {"metric": "Downtime riêng ngày", "value": downtime["duration_hours"], "unit": "hours"},
            {"metric": "Số lần downtime", "value": downtime["event_count"], "unit": "events"},
            {"metric": "OEE tích lũy đến cuối ngày", "value": oee["value"] if oee else None, "unit": "%"},
        ] + loss_groups[:3]
        trace.update(
            {
                "turn_relationship": "FOLLOW_UP_QUESTION",
                "resolved_intent": "THREE_SOURCE_DAY_SUMMARY",
                "referenced_artifact_id": chart_artifact.get("artifact_id") if chart_artifact else None,
                "selected_sources": ["machine_downtime", "loss_assignment", "apqoee_cumulative"],
                "resolved_time_range": {"date": target.isoformat(), "apqoee_as_of": target.isoformat()},
                "llm_called": llm,
                "llm_purpose": "management_commentary" if llm else None,
                "artifact_created": {"artifact_type": "THREE_SOURCE_DAY_SUMMARY", "date": target.isoformat()},
            }
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="analysis",
            title="Tổng hợp tình hình sản xuất trong ngày",
            summary=f"Ngày phân tích: {self._date_vi(target)}.\n\n{commentary}",
            table=TablePayload(columns=list(rows[0].keys()), rows=rows),
            analysis=AnalysisPayload(headline="Nhận xét quản lý", summary=commentary, table=TablePayload(columns=list(rows[0].keys()), rows=rows)),
            sources=[SourcePayload(name=downtime_source.display_name), SourcePayload(name=loss_source.display_name), SourcePayload(name=apqoee_source.display_name)],
            filters=[FilterPayload(label="Date range", operator="equals", value=target.isoformat())],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _report_create(self, conversation_id: str, question: str, artifacts: list[dict[str, Any]], chart_artifact: dict[str, Any] | None, apqoee_artifact: dict[str, Any] | None, trace: dict[str, Any]) -> ChatResponse:
        report_id = str(uuid4())
        target = self._context_day(chart_artifact)
        facts = self._report_fact_snapshot(artifacts, chart_artifact, apqoee_artifact)
        fact_hash = self._fact_hash(facts)
        fact_payload = {"facts": [fact.model_dump(mode="json") for fact in facts], "fact_hash": fact_hash, "date": target.isoformat() if target else None}
        commentary, llm = self._grounded_commentary("report_create", fact_payload)
        executive_summary = [line.strip("- ").strip() for line in commentary.splitlines() if line.strip()][:5]
        if not executive_summary:
            executive_summary = ["Báo cáo tổng hợp các kết quả phân tích đã được xác minh trong cuộc trò chuyện."]
        source_artifacts = self._report_source_artifacts(artifacts, chart_artifact, apqoee_artifact)
        sections = self._default_report_sections(commentary, chart_artifact, apqoee_artifact, source_artifacts)
        report = ReportPayload(
            report_id=report_id,
            root_report_id=report_id,
            parent_report_id=None,
            revision_number=1,
            title="Báo cáo quản trị sản xuất",
            report_type="production_day",
            subtitle=f"Tổng hợp theo ngày {self._date_vi(target)}" if target else "Tổng hợp từ các kết quả đã phân tích",
            generated_at=generated_at_vn(),
            executive_summary=executive_summary,
            kpis=self._report_kpis(facts),
            sections=sections,
            source=SourceInfo(name="Production Analytics Bundle", rows=None),
            filters=[{"label": "Date range", "value": target.isoformat() if target else None}],
            limitations=["Các nhận xét dựa trên số liệu đã xác minh; không khẳng định quan hệ nhân quả nếu chưa có phân tích nguyên nhân bổ sung."],
            completeness={
                "fact_snapshot": [fact.model_dump(mode="json") for fact in facts],
                "fact_hash": fact_hash,
                "source_artifacts": source_artifacts,
                "layout_config": {"default_sections": True, "target_page_range": "2-4"},
            },
        )
        pdf_result, downloads = self._export_report_pdf(report)
        artifact = self._build_report_artifact(report, facts, source_artifacts, pdf_result.pdf_path if pdf_result else None)
        validation = self._validate_report_payload(report, artifact)
        trace.update(
            {
                "resolved_intent": "REPORT_CREATE",
                "selected_sources": ["machine_downtime", "loss_assignment", "apqoee_cumulative"],
                "resolved_time_range": {"date": target.isoformat()} if target else None,
                "llm_called": llm,
                "llm_purpose": "report_create" if llm else None,
                "artifact_created": artifact.model_dump(mode="json"),
                "report_version_before": None,
                "report_version_after": report.revision_number,
                "fact_hash_before": None,
                "fact_hash_after": fact_hash,
                "validation_passed": validation["passed"],
                "validation_errors": validation["errors"],
                "pdf_generated": bool(pdf_result and pdf_result.pdf_path.exists()),
            }
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="report",
            title=report.title,
            summary="Đã tạo báo cáo quản trị từ các kết quả phân tích hiện có.",
            report=report,
            downloads=downloads,
            sources=[SourcePayload(name="Production Analytics Bundle")],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False, "report_validation": validation},
        )

    def _report_export(self, conversation_id: str, latest_report: dict[str, Any] | None, trace: dict[str, Any]) -> ChatResponse:
        if latest_report is None:
            return self._context_missing_response(conversation_id, "Chưa có báo cáo hiện tại để xuất PDF.")
        payload = latest_report.get("response_payload", {}).get("report") or latest_report
        report = ReportPayload.model_validate(payload).model_copy(deep=True)
        facts = self._facts_from_report(report)
        source_artifacts = list(report.completeness.get("source_artifacts", []))
        pdf_result, downloads = self._export_report_pdf(report)
        artifact = self._build_report_artifact(report, facts, source_artifacts, pdf_result.pdf_path if pdf_result else None)
        validation = self._validate_report_payload(report, artifact)
        trace.update(
            {
                "turn_relationship": "ARTIFACT_EXPORT",
                "resolved_intent": "REPORT_EXPORT",
                "referenced_artifact_id": latest_report.get("artifact_id"),
                "selected_sources": self._source_ids_from_artifacts(source_artifacts),
                "llm_called": False,
                "llm_purpose": None,
                "artifact_created": artifact.model_dump(mode="json"),
                "report_version_before": report.revision_number,
                "report_version_after": report.revision_number,
                "fact_hash_before": artifact.fact_hash,
                "fact_hash_after": artifact.fact_hash,
                "validation_passed": validation["passed"],
                "validation_errors": validation["errors"],
                "pdf_generated": bool(pdf_result and pdf_result.pdf_path.exists()),
            }
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="report",
            title=report.title,
            summary=f"Đã xuất phiên bản v{report.revision_number} hiện tại ra PDF.",
            report=report,
            downloads=downloads,
            sources=[SourcePayload(name=report.source_file_name or report.source.name)],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False, "report_validation": validation},
        )

    def _report_query(self, conversation_id: str, latest_report: dict[str, Any] | None, trace: dict[str, Any]) -> ChatResponse:
        if latest_report is None:
            return self._context_missing_response(conversation_id, "Chưa có báo cáo hiện tại để truy vấn nguồn dữ liệu.")
        payload = latest_report.get("response_payload", {}).get("report") or latest_report
        report = ReportPayload.model_validate(payload)
        source_artifacts = list(report.completeness.get("source_artifacts", []))
        rows = []
        for item in source_artifacts:
            rows.append(
                {
                    "artifact_type": item.get("artifact_type") or item.get("type") or "UNKNOWN",
                    "source": item.get("source") or item.get("source_name") or report.source.name,
                    "time_scope": json.dumps(item.get("time_range") or item.get("resolved_time_range") or item.get("date") or {}, ensure_ascii=False),
                }
            )
        if not rows:
            rows.append({"artifact_type": "REPORT_CONTEXT", "source": report.source_file_name or report.source.name, "time_scope": "Không có artifact phân tích định lượng đi kèm."})
        fact_hash = str(report.completeness.get("fact_hash") or self._fact_hash(self._facts_from_report(report)))
        trace.update(
            {
                "turn_relationship": "FOLLOW_UP_QUESTION",
                "resolved_intent": "REPORT_QUERY",
                "referenced_artifact_id": latest_report.get("artifact_id"),
                "selected_sources": self._source_ids_from_artifacts(source_artifacts),
                "llm_called": False,
                "llm_purpose": None,
                "report_version_after": report.revision_number,
                "fact_hash_after": fact_hash,
            }
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="table",
            title="Nguồn dữ liệu của báo cáo hiện tại",
            summary=f"Báo cáo v{report.revision_number} đang sử dụng snapshot fact có mã kiểm soát {fact_hash[:12]}.",
            table=TablePayload(columns=["artifact_type", "source", "time_scope"], rows=rows),
            sources=[SourcePayload(name=report.source_file_name or report.source.name)],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _report_revision(
        self,
        conversation_id: str,
        question: str,
        latest_report: dict[str, Any] | None,
        top_machine_artifact: dict[str, Any] | None,
        trace: dict[str, Any],
        *,
        export_after: bool = False,
    ) -> ChatResponse:
        if latest_report is None:
            return self._context_missing_response(conversation_id, "Chưa có báo cáo trước đó để chỉnh sửa hoặc xuất PDF.")
        payload = latest_report.get("response_payload", {}).get("report") or latest_report
        base_report = ReportPayload.model_validate(payload)
        report = base_report.model_copy(deep=True)
        operations = self._revision_operations(question)
        fact_hash_before = str(report.completeness.get("fact_hash") or self._fact_hash(self._facts_from_report(report)))
        facts = self._facts_from_report(report)
        source_artifacts = list(report.completeness.get("source_artifacts", []))
        parent_id = report.report_id
        report.report_id = str(uuid4())
        report.parent_report_id = parent_id
        report.root_report_id = report.root_report_id or parent_id
        report.revision_number = int(report.revision_number or 1) + 1
        report.generated_at = generated_at_vn()
        report.subtitle = self._revision_subtitle(report.subtitle, report.revision_number, export_after)

        llm_called = False
        if "title" in operations:
            new_title = self._extract_title(question)
            if new_title:
                report.title = new_title
        if "sources_limitations" in operations:
            self._ensure_report_section(
                report,
                PublicReportSection(
                    section_type="sources",
                    title="Nguồn dữ liệu và giới hạn phân tích",
                    summary="Báo cáo sử dụng snapshot fact đã khóa từ các artifact phân tích hiện có; các diễn giải không được thay đổi số liệu nguồn.",
                    commentary=["Nguồn, bộ lọc và giới hạn được giữ minh bạch để tránh diễn giải vượt phạm vi dữ liệu."],
                ),
            )
            report.limitations = _dedupe_lines(report.limitations + ["Snapshot fact của báo cáo được giữ nguyên qua revision; mọi thay đổi chỉ ở phần diễn đạt hoặc cấu trúc."])
        if "remove_limitations" in operations:
            report.limitations = []
            report.sections = [section for section in report.sections if section.section_type not in {"limitations", "nguon_va_gioi_han"}]
            for section in report.sections:
                if section.section_type == "sources":
                    section.title = "Nguồn dữ liệu"
                    section.summary = "Báo cáo sử dụng snapshot fact đã khóa từ các artifact phân tích hiện có."
                    section.commentary = ["Nguồn và bộ lọc được giữ minh bạch theo artifact gốc của báo cáo."]
        if "shorten" in operations:
            report.detail_level = "CONCISE"
            report.target_page_range = "1-2"
            report.executive_summary = report.executive_summary[:3]
            report.sections = self._compact_report_sections(report.sections)
        if "top_machines" in operations:
            self._apply_top_machine_section(report, top_machine_artifact)
        if any(op in operations for op in ["management_detail", "management_style", "shorten"]):
            revised_text, llm = self._grounded_commentary(
                "report_revision",
                {
                    "operations": operations,
                    "fact_hash": fact_hash_before,
                    "facts": [fact.model_dump(mode="json") for fact in facts],
                    "current_title": report.title,
                },
            )
            llm_called = llm_called or llm
            self._replace_management_commentary(report, revised_text, detailed="management_detail" in operations)

        if not operations:
            revised_text, llm = self._grounded_commentary("report_revision", {"fact_hash": fact_hash_before, "facts": [fact.model_dump(mode="json") for fact in facts]})
            llm_called = llm_called or llm
            self._replace_management_commentary(report, revised_text, detailed=True)
            operations = ["management_detail"]
        if not llm_called:
            _audit_text, llm = self._grounded_commentary(
                "report_revision_validation",
                {"operations": operations, "fact_hash": fact_hash_before, "facts": [fact.model_dump(mode="json") for fact in facts]},
            )
            llm_called = llm_called or llm

        report.completeness = {
            **(report.completeness or {}),
            "fact_snapshot": [fact.model_dump(mode="json") for fact in facts],
            "fact_hash": fact_hash_before,
            "source_artifacts": source_artifacts,
            "revision_operations": operations,
            "layout_config": {"target_page_range": report.target_page_range, "detail_level": report.detail_level},
        }
        pdf_result, downloads = self._export_report_pdf(report)
        artifact = self._build_report_artifact(report, facts, source_artifacts, pdf_result.pdf_path if pdf_result else None)
        validation = self._validate_report_payload(report, artifact, expected_fact_hash=fact_hash_before)
        trace.update(
            {
                "turn_relationship": "FOLLOW_UP_QUESTION",
                "resolved_intent": "REPORT_REVISE_EXPORT" if export_after else "REPORT_REVISE",
                "referenced_artifact_id": latest_report.get("artifact_id"),
                "selected_sources": self._source_ids_from_artifacts(source_artifacts),
                "llm_called": llm_called,
                "llm_purpose": "report_revision" if llm_called else None,
                "artifact_created": artifact.model_dump(mode="json"),
                "report_version_before": base_report.revision_number,
                "report_version_after": report.revision_number,
                "revision_operations": operations,
                "fact_hash_before": fact_hash_before,
                "fact_hash_after": artifact.fact_hash,
                "validation_passed": validation["passed"],
                "validation_errors": validation["errors"],
                "pdf_generated": bool(pdf_result and pdf_result.pdf_path.exists()),
            }
        )
        summary = f"Đã tạo phiên bản v{report.revision_number}"
        summary += " và xuất PDF." if export_after else " của báo cáo."
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="report",
            title=report.title,
            summary=summary,
            report=report,
            downloads=downloads,
            sources=[SourcePayload(name=report.source_file_name or report.source.name)],
            metadata={"status": "COMPLETED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False, "report_validation": validation},
        )

    def _report_fact_snapshot(self, artifacts: list[dict[str, Any]], chart_artifact: dict[str, Any] | None, apqoee_artifact: dict[str, Any] | None) -> list[VerifiedFact]:
        facts: list[VerifiedFact] = []
        if chart_artifact:
            facts.append(
                VerifiedFact(
                    fact_id="daily_downtime.highest_value",
                    artifact_id=str(chart_artifact.get("artifact_id") or ""),
                    artifact_type="DAILY_DOWNTIME_CHART",
                    label="Downtime cao nhất trong khoảng",
                    value=chart_artifact.get("highest_value"),
                    unit="hours",
                    time_scope={"date": chart_artifact.get("highest_date"), **(chart_artifact.get("time_range") or {})},
                    source=str(chart_artifact.get("source") or "MACHINE_DOWNTIME"),
                )
            )
        if apqoee_artifact:
            payload = apqoee_artifact.get("response_payload") or {}
            table = payload.get("table") or {}
            for row in (table.get("rows") or [])[:4]:
                metric = _row_get(row, "metric", "Chỉ số", "Chi so", "Chá»‰ sá»‘")
                value, unit = _split_value_unit(
                    _row_get(row, "value", "Giá trị", "Gia tri", "GiÃ¡ trá»‹"),
                    _row_get(row, "unit", "Đơn vị", "Don vi", "ÄÆ¡n vá»‹"),
                )
                time_scope = _row_get(row, "time_scope", "Phạm vi thời gian", "Pham vi thoi gian", "Pháº¡m vi thá»i gian")
                facts.append(
                    VerifiedFact(
                        fact_id=f"apqoee.{metric or 'metric'}",
                        artifact_id=str(apqoee_artifact.get("artifact_id") or ""),
                        artifact_type="APQOEE_SNAPSHOT",
                        label=str(metric or "APQOEE"),
                        value=value,
                        unit=str(unit or "%"),
                        time_scope={"as_of_date": time_scope or apqoee_artifact.get("as_of_date")},
                        source="APQOEE_CUMULATIVE",
                    )
                )
        for item in artifacts:
            payload = item.get("payload") or {}
            created = _artifact_created_from_payload(payload)
            if not isinstance(created, dict) or created.get("artifact_type") in {None, "REPORT_ARTIFACT", "DAILY_DOWNTIME_CHART", "APQOEE_SNAPSHOT"}:
                continue
            response_table = payload.get("table") if isinstance(payload.get("table"), dict) else None
            value = (response_table or {}).get("rows", [])[:5] if response_table else created
            facts.append(
                VerifiedFact(
                    fact_id=f"{created.get('artifact_type')}.{item.get('artifact_id') or len(facts)}",
                    artifact_id=str(item.get("artifact_id") or ""),
                    artifact_type=str(created.get("artifact_type")),
                    label=str(created.get("artifact_type")).replace("_", " ").title(),
                    value=value,
                    unit=None,
                    time_scope=created.get("time_range") or {"date": created.get("date")},
                    source=str(created.get("source") or ""),
                )
            )
        if not facts:
            facts.append(
                VerifiedFact(
                    fact_id="report_context.no_quantitative_artifact",
                    artifact_type="REPORT_CONTEXT",
                    label="Trạng thái dữ liệu định lượng",
                    value="Chưa có artifact phân tích định lượng được ghi nhận trong ngữ cảnh báo cáo.",
                    source="Production Analytics Bundle",
                )
            )
        return facts

    def _report_source_artifacts(self, artifacts: list[dict[str, Any]], chart_artifact: dict[str, Any] | None, apqoee_artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in [chart_artifact, apqoee_artifact]:
            if item:
                candidates.append(item)
        for item in artifacts:
            payload = item.get("payload") or {}
            created = _artifact_created_from_payload(payload)
            if isinstance(created, dict) and created.get("artifact_type") != "REPORT_ARTIFACT":
                candidates.append({"artifact_id": item.get("artifact_id"), **created})
        compact: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            key = f"{item.get('artifact_id')}:{item.get('artifact_type')}:{item.get('date') or item.get('highest_date') or item.get('as_of_date')}"
            if key in seen:
                continue
            seen.add(key)
            compact.append({k: v for k, v in item.items() if k != "response_payload"})
        return compact

    def _facts_from_report(self, report: ReportPayload) -> list[VerifiedFact]:
        raw = report.completeness.get("fact_snapshot") or []
        facts = []
        for item in raw:
            if isinstance(item, dict):
                facts.append(VerifiedFact.model_validate(item))
        if facts:
            return facts
        legacy = report.completeness.get("facts")
        return [
            VerifiedFact(
                fact_id="legacy_report.facts",
                artifact_type="REPORT_CONTEXT",
                label="Snapshot fact kế thừa",
                value=legacy or "Không có snapshot fact chi tiết trong báo cáo kế thừa.",
                source=report.source.name,
            )
        ]

    def _fact_hash(self, facts: list[VerifiedFact]) -> str:
        payload = [fact.model_dump(mode="json") for fact in facts]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _default_report_sections(self, commentary: str, chart_artifact: dict[str, Any] | None, apqoee_artifact: dict[str, Any] | None, source_artifacts: list[dict[str, Any]]) -> list[PublicReportSection]:
        sections = [
            PublicReportSection(
                section_type="report_info",
                title="Thông tin báo cáo",
                summary="Báo cáo được lập từ các artifact phân tích đã có trong cuộc trò chuyện hiện tại.",
            ),
            PublicReportSection(section_type="management_comments", title="Nhận xét quản lý", summary=commentary, commentary=[commentary]),
        ]
        chart_payload = ((chart_artifact or {}).get("response_payload") or {}).get("chart") if chart_artifact else None
        if isinstance(chart_payload, dict):
            sections.append(
                PublicReportSection(
                    section_type="daily_downtime_chart",
                    title="Xu hướng downtime theo ngày",
                    summary="Biểu đồ này được lấy trực tiếp từ artifact downtime đã tạo trước đó.",
                    chart=ChartPayload.model_validate(chart_payload),
                )
            )
        apqoee_table = ((apqoee_artifact or {}).get("response_payload") or {}).get("table") if apqoee_artifact else None
        if isinstance(apqoee_table, dict) and apqoee_table.get("rows"):
            sections.append(
                PublicReportSection(
                    section_type="apqoee_snapshot",
                    title="KPI APQOEE tích lũy",
                    summary="Các chỉ số APQOEE được giữ nguyên theo snapshot đã xác minh.",
                    table=TablePayload.model_validate(apqoee_table),
                )
            )
        sections.append(
            PublicReportSection(
                section_type="sources",
                title="Nguồn dữ liệu và giới hạn phân tích",
                summary=f"Báo cáo sử dụng {len(source_artifacts)} artifact nguồn đã ghi nhận trong conversation.",
                commentary=["Không bổ sung số liệu ngoài các artifact nguồn đã lưu trong snapshot fact."],
            )
        )
        return sections

    def _report_kpis(self, facts: list[VerifiedFact]) -> list[KpiCard]:
        cards: list[KpiCard] = []
        for fact in facts:
            if fact.value is None or isinstance(fact.value, (dict, list)):
                continue
            cards.append(KpiCard(label=fact.label[:60], value=str(fact.value), unit=fact.unit, hint=fact.source))
            if len(cards) == 4:
                break
        return cards

    def _revision_operations(self, question: str) -> list[str]:
        text = normalize_text(question)
        operations: list[str] = []
        if "doi tieu de" in text:
            operations.append("title")
        if "chi tiet" in text or "nhan xet" in text:
            operations.append("management_detail")
        if "phong cach" in text or "quan ly nha may" in text:
            operations.append("management_style")
        if "nguon du lieu" in text or "gioi han" in text:
            operations.append("sources_limitations")
        if "rut gon" in text or "2 trang" in text or "hai trang" in text:
            operations.append("shorten")
        if "top 5" in text and "may" in text:
            operations.append("top_machines")
        if "bo phan" in text and "gioi han" in text:
            operations = [op for op in operations if op != "sources_limitations"]
            operations.append("remove_limitations")
        return list(dict.fromkeys(operations))

    def _extract_title(self, question: str) -> str | None:
        lower = question.lower()
        for marker in [" thành ", " thanh "]:
            idx = lower.find(marker)
            if idx >= 0:
                title = question[idx + len(marker) :].strip()
                title = re.sub(r"[.!?]+$", "", title).strip("\"' ")
                return title[:140] if title else None
        match = re.search(r"(?:thành|thanh)\s+(.+?)(?:[.!?]|$)", question, flags=re.IGNORECASE)
        if not match:
            return None
        title = " ".join(match.group(1).split()).strip("\"' ")
        return title[:140] if title else None

    def _revision_subtitle(self, subtitle: str | None, version: int, export_after: bool) -> str:
        base = re.sub(r"\s+-\s+phiên bản v\d+.*$", "", subtitle or "Báo cáo quản trị", flags=re.IGNORECASE)
        suffix = f"phiên bản v{version}"
        if export_after:
            suffix += ", đã xuất PDF"
        return f"{base} - {suffix}"

    def _ensure_report_section(self, report: ReportPayload, section: PublicReportSection) -> None:
        report.sections = [existing for existing in report.sections if existing.section_type != section.section_type] + [section]

    def _replace_management_commentary(self, report: ReportPayload, text: str, *, detailed: bool) -> None:
        commentary = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        if detailed and len(commentary) < 2:
            commentary.append("Nhận xét này chỉ thay đổi cách diễn đạt quản lý; snapshot fact và toàn bộ số liệu được giữ nguyên.")
        section = next((item for item in report.sections if item.section_type in {"management_comments", "summary", "nhan_xet_quan_ly"} or "Nhận xét" in item.title), None)
        if section is None:
            report.sections.insert(1, PublicReportSection(section_type="management_comments", title="Nhận xét quản lý", summary="\n".join(commentary), commentary=commentary))
            return
        section.summary = "\n".join(commentary)
        section.commentary = commentary

    def _compact_report_sections(self, sections: list[PublicReportSection]) -> list[PublicReportSection]:
        compact: list[PublicReportSection] = []
        for section in sections:
            item = section.model_copy(deep=True)
            item.commentary = item.commentary[:2]
            if item.table and len(item.table.rows) > 5:
                item.table = TablePayload(columns=item.table.columns, rows=item.table.rows[:5])
            compact.append(item)
        return compact

    def _apply_top_machine_section(self, report: ReportPayload, top_machine_artifact: dict[str, Any] | None) -> None:
        table_payload = ((top_machine_artifact or {}).get("response_payload") or {}).get("table") if top_machine_artifact else None
        if isinstance(table_payload, dict) and table_payload.get("rows"):
            table = TablePayload.model_validate(table_payload)
            table.rows = table.rows[:5]
            section = PublicReportSection(
                section_type="top_machines",
                title="Top 5 máy có downtime cao nhất",
                summary="Bảng được lấy từ artifact drill-down máy đã có trong conversation.",
                table=table,
            )
        else:
            section = PublicReportSection(
                section_type="top_machines_missing",
                title="Top 5 máy có downtime cao nhất",
                summary="Chưa có artifact xếp hạng máy theo downtime trong ngữ cảnh báo cáo hiện tại, nên báo cáo không tự tạo bảng số liệu mới.",
                commentary=["Hãy tạo phân tích top máy downtime trước nếu cần đưa bảng định lượng vào báo cáo."],
            )
        self._ensure_report_section(report, section)

    def _export_report_pdf(self, report: ReportPayload) -> tuple[Any | None, list[DownloadPayload]]:
        try:
            pdf_result = export_public_report_pdf(report, self.settings.reports_dir)
        except Exception:
            report.pdf_status = "failed"
            report.pdf_download_url = None
            return None, []
        report.pdf_status = "ready" if pdf_result.pdf_path.exists() else "failed"
        report.pdf_download_url = f"/api/artifacts/{pdf_result.pdf_path.name}/download" if pdf_result.pdf_path.exists() else None
        downloads = [DownloadPayload(id=pdf_result.pdf_path.name, filename=pdf_result.pdf_path.name, label="Tải báo cáo PDF", mime_type="application/pdf")] if pdf_result.pdf_path.exists() else []
        return pdf_result, downloads

    def _build_report_artifact(self, report: ReportPayload, facts: list[VerifiedFact], source_artifacts: list[dict[str, Any]], pdf_path: Path | None) -> ReportArtifact:
        fact_hash = self._fact_hash(facts)
        return ReportArtifact(
            report_id=report.report_id,
            root_report_id=report.root_report_id or report.report_id,
            parent_report_id=report.parent_report_id,
            version=int(report.revision_number or 1),
            scope=ReportScope(source_name=report.source_file_name or report.source.name, time_range=report.date_range, filters=report.filters),
            source_artifacts=source_artifacts,
            fact_snapshot=facts,
            fact_hash=fact_hash,
            sections=[section.section_type for section in report.sections],
            layout_config=report.completeness.get("layout_config") or {"target_page_range": report.target_page_range, "detail_level": report.detail_level},
            pdf_path=str(pdf_path) if pdf_path else None,
            pdf_status=report.pdf_status,
        )

    def _validate_report_payload(self, report: ReportPayload, artifact: ReportArtifact, expected_fact_hash: str | None = None) -> dict[str, Any]:
        errors: list[str] = []
        if expected_fact_hash and artifact.fact_hash != expected_fact_hash:
            errors.append("FACT_HASH_CHANGED")
        if not artifact.fact_snapshot:
            errors.append("MISSING_FACT_SNAPSHOT")
        section_types = [section.section_type for section in report.sections]
        if len(section_types) != len(set(section_types)):
            errors.append("DUPLICATE_SECTIONS")
        for section in report.sections:
            has_content = bool(section.summary or section.commentary or section.kpis or section.table or section.chart)
            if not section.title.strip() or not has_content:
                errors.append(f"EMPTY_SECTION:{section.section_type}")
        payload_text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, default=str)
        forbidden = ["NaN", "fallback", "execution_mode", "query_plan_id", "DEMO READY", "Demo", "Gopak"]
        leaked = [token for token in forbidden if token in payload_text]
        if leaked:
            errors.append(f"FORBIDDEN_TOKENS:{','.join(leaked)}")
        return {"passed": not errors, "errors": errors, "fact_hash": artifact.fact_hash}

    def _source_ids_from_artifacts(self, source_artifacts: list[dict[str, Any]]) -> list[str]:
        values = [str(item.get("source") or item.get("source_id") or "") for item in source_artifacts]
        return [value for value in dict.fromkeys(values) if value]

    def _special_response(self, conversation_id: str, question: str, sources: list[ProductionSource]) -> ChatResponse | None:
        text = normalize_text(question)
        if any(term in text for term in ["schema", "cot", "column"]):
            rows = []
            for source in sources:
                if source.status != "ready":
                    continue
                df, roles = self._preview_dataframe(source)
                for column in df.columns:
                    rows.append(
                        {
                            "source_id": source.source_id,
                            "source": source.display_name,
                            "column": column,
                            "dtype": str(df[column].dtype),
                            "semantic_role": roles.get(column),
                        }
                    )
            return self._metadata_table_response(conversation_id, "schema", "Production source schema", rows, sources, "SCHEMA")
        if any(term in text for term in ["dong mau", "sample", "mau"]):
            route = SourceRouter(sources).route(question)
            source_id = route.source_ids[0] if route.source_ids else "machine_downtime"
            source = next(source for source in sources if source.source_id == source_id)
            df, _roles = self._preview_dataframe(source)
            rows = df.head(5).astype(object).where(pd.notna(df), None).to_dict(orient="records")
            return self._metadata_table_response(conversation_id, "sample_table", f"Sample rows: {source.display_name}", rows, [source], "SAMPLE_TABLE")
        if any(term in text for term in ["data", "du lieu", "file co gi", "nhung file", "tu ngay nao", "noi dung"]):
            rows = []
            for source in sources:
                if source.status != "ready":
                    continue
                df, _roles = self._preview_dataframe(source)
                rows.append(
                    {
                        "source_id": source.source_id,
                        "source": source.display_name,
                        "rows": int(len(df)),
                        "columns": int(len(df.columns)),
                        "grain": source.primary_grain,
                        "checksum": source.checksum,
                    }
                )
            return self._metadata_table_response(conversation_id, "data_overview", "Production Analytics Bundle", rows, sources, "DATA_OVERVIEW")
        return None

    def _preview_dataframe(self, source: ProductionSource) -> tuple[pd.DataFrame, dict[str, str]]:
        from src.production.ingestion import _load_source_dataframe

        return _load_source_dataframe(source)

    def _metadata_table_response(
        self,
        conversation_id: str,
        response_type: str,
        title: str,
        rows: list[dict[str, Any]],
        sources: list[ProductionSource],
        execution_mode: str,
    ) -> ChatResponse:
        table = TablePayload(columns=list(rows[0].keys()) if rows else [], rows=rows)
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,  # type: ignore[arg-type]
            title=title,
            summary=f"{title}: {len(rows)} rows returned.",
            table=table,
            sources=[SourcePayload(name=source.display_name) for source in sources if source.status == "ready"],
            filters=[],
            downloads=[],
            metadata={
                "status": "COMPLETED",
                "sources_used": [source.source_id for source in sources if source.status == "ready"],
                "time_scope": {"label": "metadata", "business_timezone": self.settings.business_timezone or None},
                "metric_scope": ["metadata"],
                "data_version": {source.source_id: {"checksum": source.checksum, "schema_fingerprint": source.schema_fingerprint} for source in sources},
                "execution_mode": execution_mode,
                "fallback_used": False,
                "generated_sql": None,
                "file_scope_validated": True,
            },
        )

    def registry_health(self) -> dict[str, Any]:
        return self.registry.health()

    def _terminal_response(
        self,
        conversation_id: str,
        route: SourceRoute,
        response_type: str,
        title: str,
        summary: str,
        *,
        state: str = "CLARIFICATION_REQUIRED",
    ) -> ChatResponse:
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            sources=[],
            filters=[],
            downloads=[],
            metadata={
                "status": state,
                "sources_used": list(route.source_ids),
                "time_scope": {},
                "metric_scope": list(route.requested_metrics),
                "data_version": {},
                "source_route": route.to_dict(),
                "execution_mode": "DETERMINISTIC_PRODUCTION",
                "fallback_used": False,
            },
        )

    def _render_response(self, conversation_id: str, evidence: EvidencePack, sources: dict[str, ProductionSource]) -> ChatResponse:
        table = TablePayload(columns=list(evidence.rows[0].keys()) if evidence.rows else [], rows=evidence.rows)
        source_payloads = [SourcePayload(name=sources[source_id].display_name) for source_id in evidence.sources_used if source_id in sources]
        title = "Production analytics result"
        if len(evidence.sources_used) == 1:
            title = sources[evidence.sources_used[0]].display_name
        summary_parts = []
        for row in evidence.rows:
            metric = row.get("metric")
            value = row.get("value")
            unit = row.get("unit")
            scope = row.get("time_scope")
            if metric and value is not None:
                suffix = f" {unit}" if unit else ""
                summary_parts.append(f"{metric}: {value}{suffix} ({scope})")
        summary = "; ".join(summary_parts[:4]) if summary_parts else "The requested sources were evaluated with deterministic calculations."
        if evidence.notes:
            summary += " " + " ".join(evidence.notes[:2])

        analysis = AnalysisPayload(
            headline=title,
            summary=summary,
            insights=[
                AnalysisInsight(text=note, evidence=[source_id for source_id in evidence.sources_used])
                for note in evidence.notes[:5]
            ],
            table=table,
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="analysis" if len(evidence.sources_used) > 1 else "table",
            title=title,
            summary=summary,
            primary_value=str(evidence.rows[0].get("value")) if len(evidence.rows) == 1 else None,
            secondary_value=str(evidence.rows[0].get("unit")) if len(evidence.rows) == 1 else None,
            table=table,
            analysis=analysis if len(evidence.sources_used) > 1 else None,
            sources=source_payloads,
            filters=[
                FilterPayload(label="Sources", operator="in", value=evidence.sources_used),
                FilterPayload(label="Time scope", operator="equals", value=evidence.time_scope.get("label")),
            ],
            downloads=[],
            metadata={
                "status": "COMPLETED",
                "sources_used": evidence.sources_used,
                "time_scope": evidence.time_scope,
                "metric_scope": evidence.metric_scope,
                "data_version": evidence.data_version,
                "source_route": evidence.route,
                "execution_plans": evidence.execution_plans,
                "execution_mode": "DETERMINISTIC_PRODUCTION",
                "fallback_used": False,
            },
        )

    def _plan_for_source(self, question: str, route: SourceRoute, source: ProductionSource) -> ExecutionPlan:
        text = normalize_text(question)
        window = self._resolve_time_window(question, source.source_id)
        if source.source_id == "apqoee_cumulative":
            if self._is_period_specific_oee(text):
                if self.settings.performance_formula_mode in {"", "disabled"}:
                    return ExecutionPlan(
                        source_id=source.source_id,
                        operation="apqoee_period_unsupported",
                        metric_scope=["period_oee"],
                        time_scope=self._window_dict(window),
                        grain="period",
                    )
            operation = "apqoee_trend" if route.time_semantics == "trend" else "apqoee_as_of"
            return ExecutionPlan(source_id=source.source_id, operation=operation, metric_scope=list(route.requested_metrics), time_scope=self._window_dict(window), grain=route.requested_grain)
        if source.source_id == "machine_downtime":
            return ExecutionPlan(source_id=source.source_id, operation="downtime_interval", metric_scope=["downtime_duration", "downtime_count"], time_scope=self._window_dict(window), grain=route.requested_grain)
        if source.source_id == "loss_assignment":
            return ExecutionPlan(source_id=source.source_id, operation="loss_interval", metric_scope=["loss_duration", "loss_count"], time_scope=self._window_dict(window), grain=route.requested_grain)
        raise ValueError(f"Unsupported source: {source.source_id}")

    def _execute_plan(self, source: ProductionSource, plan: ExecutionPlan) -> tuple[list[dict[str, Any]], list[str]]:
        if plan.operation == "apqoee_period_unsupported":
            raise UnsupportedCalculation("Period-specific APQOEE/OEE is locked until PERFORMANCE_FORMULA_MODE is configured with an approved Performance formula.")
        if plan.operation in {"apqoee_as_of", "apqoee_trend"}:
            return self._execute_apqoee(source, plan)
        if plan.operation in {"downtime_interval", "loss_interval"}:
            return self._execute_events(source, plan)
        raise ValueError(f"Unsupported operation: {plan.operation}")

    def _execute_apqoee(self, source: ProductionSource, plan: ExecutionPlan) -> tuple[list[dict[str, Any]], list[str]]:
        df = pd.read_excel(source.workbook_path, sheet_name=0)
        required = {"ExecuteAt", "OEE", "Availability", "Performance", "Quality"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"APQOEE workbook is missing columns: {', '.join(sorted(missing))}")
        local_tz = self._business_zone()
        df["_execute_utc"] = pd.to_datetime(df["ExecuteAt"], utc=True, errors="coerce")
        df = df.dropna(subset=["_execute_utc"]).sort_values("_execute_utc")
        df["_execute_local"] = df["_execute_utc"].dt.tz_convert(local_tz)
        if plan.operation == "apqoee_trend":
            daily = df.groupby(df["_execute_local"].dt.date, as_index=False).tail(1)
            rows = [
                {
                    "source_id": source.source_id,
                    "source": source.display_name,
                    "metric": "Cumulative OEE",
                    "value": round(float(row["OEE"]) * 100, 2),
                    "unit": "%",
                    "time_scope": "cumulative snapshot trend",
                    "snapshot_time": row["_execute_local"].isoformat(),
                }
                for _, row in daily.tail(90).iterrows()
            ]
            return rows, ["Đây là xu hướng OEE tích lũy, không phải OEE riêng từng ngày."]

        end = self._plan_end(plan, df["_execute_local"].max().to_pydatetime())
        eligible = df[df["_execute_local"] <= pd.Timestamp(end)]
        if eligible.empty:
            raise ValueError("No APQOEE snapshot exists at or before the requested time.")
        row = eligible.iloc[-1]
        local_time = row["_execute_local"].isoformat()
        rows = [
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": "Cumulative OEE",
                "value": round(float(row["OEE"]) * 100, 2),
                "unit": "%",
                "time_scope": f"cumulative through {local_time}",
                "snapshot_time": local_time,
            },
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": "Cumulative Availability",
                "value": round(float(row["Availability"]) * 100, 2),
                "unit": "%",
                "time_scope": f"cumulative through {local_time}",
                "snapshot_time": local_time,
            },
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": "Cumulative Performance",
                "value": round(float(row["Performance"]) * 100, 2),
                "unit": "%",
                "time_scope": f"cumulative through {local_time}",
                "snapshot_time": local_time,
            },
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": "Cumulative Quality",
                "value": round(float(row["Quality"]) * 100, 2),
                "unit": "%",
                "time_scope": f"cumulative through {local_time}",
                "snapshot_time": local_time,
            },
        ]
        return rows, ["Các chỉ số APQOEE là giá trị tích lũy từ đầu tập dữ liệu đến thời điểm snapshot được chọn."]

    def _execute_events(self, source: ProductionSource, plan: ExecutionPlan) -> tuple[list[dict[str, Any]], list[str]]:
        df = self._load_event_workbook(source.workbook_path)
        start, end = self._event_window(plan, df)
        clipped_start = df["start_time"].clip(lower=start)
        effective_end = df["end_time"].fillna(end).clip(upper=end)
        overlaps = (df["start_time"] < end) & (df["end_time"].fillna(end) >= start)
        working = df[overlaps].copy()
        if working.empty:
            duration_seconds = 0.0
            count = 0
            machines = 0
        else:
            working["_effective_start"] = clipped_start[overlaps]
            working["_effective_end"] = effective_end[overlaps]
            seconds = (working["_effective_end"] - working["_effective_start"]).dt.total_seconds().clip(lower=0)
            duration_seconds = float(seconds.sum())
            count = int(len(working))
            machines = int(working["machine"].nunique(dropna=True))
        label = "Downtime" if source.source_id == "machine_downtime" else "Loss"
        rows = [
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": f"{label} duration",
                "value": round(duration_seconds / 3600, 2),
                "unit": "hours",
                "time_scope": f"{start.isoformat()} to {end.isoformat()}",
            },
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": f"{label} event count",
                "value": count,
                "unit": "events",
                "time_scope": f"{start.isoformat()} to {end.isoformat()}",
            },
            {
                "source_id": source.source_id,
                "source": source.display_name,
                "metric": "Affected machines",
                "value": machines,
                "unit": "machines",
                "time_scope": f"{start.isoformat()} to {end.isoformat()}",
            },
        ]
        note = (
            "Downtime được tính theo phần thời gian giao với khoảng được yêu cầu."
            if source.source_id == "machine_downtime"
            else "Tổn thất được tính theo phần thời gian giao với khoảng được yêu cầu."
        )
        notes = [note]
        return rows, notes

    def _load_event_workbook(self, path) -> pd.DataFrame:
        df = pd.read_excel(path, sheet_name=0, header=34)
        mapping = {
            "Máy": "machine",
            "Thời gian bắt đầu": "start_time",
            "Thời gian kết thúc": "end_time",
            "Thời lượng": "duration_text",
            "Tên tổn thất": "loss_name",
            "Nhóm tổn thất": "loss_group",
            "Loại tổn thất": "loss_type",
        }
        df = df.rename(columns=mapping)
        required = {"machine", "start_time", "end_time"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Event workbook is missing columns: {', '.join(sorted(missing))}")
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
        return df.dropna(subset=["start_time"])

    def _explicit_date_from_text(self, text: str) -> date | None:
        for pattern in [r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b"]:
            match = re.search(pattern, text)
            if not match:
                continue
            parts = match.groups()
            if len(parts) == 3 and len(parts[0]) == 4:
                year, month, day = [int(part) for part in parts]
            else:
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2] or 2025)
            return date(year, month, day)
        day_match = re.search(r"\b(?:ngay|day)\s+(\d{1,2})\b", text)
        if day_match:
            return date(2025, 11, int(day_match.group(1)))
        return None

    def _date_range_from_text(self, question: str) -> tuple[date, date]:
        text = normalize_text(question)
        match = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?.{0,30}?(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            d1, m1, y1, d2, m2, y2 = match.groups()
            year = int(y1 or y2)
            return date(year, int(m1), int(d1)), date(int(y2), int(m2), int(d2))
        explicit = self._explicit_date_from_text(text)
        if explicit:
            return explicit, explicit
        return date(2025, 11, 3), date(2025, 11, 15)

    def _latest_apqoee_date(self, source: ProductionSource) -> date:
        df = pd.read_excel(source.workbook_path, sheet_name=0)
        local_tz = self._business_zone()
        times = pd.to_datetime(df["ExecuteAt"], utc=True, errors="coerce").dropna().dt.tz_convert(local_tz)
        return max(ts.date() for ts in times)

    def _apqoee_snapshot_rows(self, source: ProductionSource, target: date) -> list[dict[str, Any]]:
        local_tz = self._business_zone()
        end = datetime.combine(target + timedelta(days=1), time.min, tzinfo=local_tz)
        plan = ExecutionPlan(
            source_id="apqoee_cumulative",
            operation="apqoee_as_of",
            metric_scope=["oee", "availability", "performance", "quality"],
            time_scope={"start": None, "end": end.isoformat(), "label": target.isoformat(), "resolution": "as_of_date"},
            grain="cumulative_as_of",
        )
        rows, _notes = self._execute_apqoee(source, plan)
        return rows

    def _daily_event_rows(self, source: ProductionSource, start_date: date, end_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        current = start_date
        while current <= end_date:
            totals = self._event_totals_for_day(source, current)
            rows.append(
                {
                    "date": current.isoformat(),
                    "date_label": current.strftime("%d/%m/%Y"),
                    "downtime_hours": totals["duration_hours"],
                    "event_count": totals["event_count"],
                    "affected_machines": totals["affected_machines"],
                }
            )
            current += timedelta(days=1)
        return rows

    def _event_totals_for_day(self, source: ProductionSource, target: date) -> dict[str, Any]:
        df = self._load_event_workbook(source.workbook_path)
        start = pd.Timestamp(datetime.combine(target, time.min))
        end = pd.Timestamp(datetime.combine(target + timedelta(days=1), time.min))
        working = self._events_overlapping_window(df, start, end)
        if working.empty:
            return {"duration_hours": 0.0, "event_count": 0, "affected_machines": 0}
        seconds = (working["_effective_end"] - working["_effective_start"]).dt.total_seconds().clip(lower=0)
        return {
            "duration_hours": round(float(seconds.sum()) / 3600, 2),
            "event_count": int(len(working)),
            "affected_machines": int(working["machine"].nunique(dropna=True)),
        }

    def _events_overlapping_window(self, df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        effective_end = df["end_time"].fillna(end).clip(upper=end)
        clipped_start = df["start_time"].clip(lower=start)
        overlaps = (df["start_time"] < end) & (df["end_time"].fillna(end) >= start)
        working = df[overlaps].copy()
        if working.empty:
            return working
        working["_effective_start"] = clipped_start[overlaps]
        working["_effective_end"] = effective_end[overlaps]
        return working

    def _top_machines_for_day(self, source: ProductionSource, target: date, limit: int) -> list[dict[str, Any]]:
        df = self._load_event_workbook(source.workbook_path)
        start = pd.Timestamp(datetime.combine(target, time.min))
        end = pd.Timestamp(datetime.combine(target + timedelta(days=1), time.min))
        working = self._events_overlapping_window(df, start, end)
        if working.empty:
            return []
        working["_duration_hours"] = (working["_effective_end"] - working["_effective_start"]).dt.total_seconds().clip(lower=0) / 3600
        grouped = (
            working.groupby("machine", dropna=False)
            .agg(downtime_hours=("_duration_hours", "sum"), event_count=("machine", "size"))
            .reset_index()
            .sort_values("downtime_hours", ascending=False)
            .head(limit)
        )
        return [
            {"machine": str(row["machine"]), "downtime_hours": round(float(row["downtime_hours"]), 2), "event_count": int(row["event_count"])}
            for _, row in grouped.iterrows()
        ]

    def _loss_groups_for_day(self, source: ProductionSource, target: date, limit: int) -> list[dict[str, Any]]:
        df = self._load_event_workbook(source.workbook_path)
        start = pd.Timestamp(datetime.combine(target, time.min))
        end = pd.Timestamp(datetime.combine(target + timedelta(days=1), time.min))
        working = self._events_overlapping_window(df, start, end)
        if working.empty:
            return []
        working["_duration_hours"] = (working["_effective_end"] - working["_effective_start"]).dt.total_seconds().clip(lower=0) / 3600
        group_col = "loss_group" if "loss_group" in working.columns else "loss_name"
        grouped = (
            working.groupby(group_col, dropna=False)
            .agg(value=("_duration_hours", "sum"), event_count=(group_col, "size"))
            .reset_index()
            .sort_values("value", ascending=False)
            .head(limit)
        )
        return [
            {"metric": "Nhóm tổn thất nổi bật", "loss_group": str(row[group_col]), "value": round(float(row["value"]), 2), "event_count": int(row["event_count"]), "unit": "hours"}
            for _, row in grouped.iterrows()
        ]

    def _context_day(self, chart_artifact: dict[str, Any] | None) -> date | None:
        if chart_artifact and chart_artifact.get("highest_date"):
            return date.fromisoformat(str(chart_artifact["highest_date"]))
        return None

    def _context_missing_response(self, conversation_id: str, summary: str) -> ChatResponse:
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="clarification",
            title="Cần thêm ngữ cảnh",
            summary=summary,
            metadata={"status": "CONTEXT_REQUIRED", "execution_mode": "ORCHESTRATED_PRODUCTION", "fallback_used": False},
        )

    def _grounded_commentary(self, purpose: str, facts: dict[str, Any]) -> tuple[str, bool]:
        prompt = (
            "Bạn là trợ lý phân tích sản xuất. Chỉ viết tiếng Việt. "
            "Dựa duy nhất trên JSON facts đã xác minh, viết 2-3 gạch đầu dòng ngắn. "
            "Không nhắc JSON, model, fallback, schema hay khóa nội bộ.\n\n"
            f"Purpose: {purpose}\nFacts: {json.dumps(facts, ensure_ascii=False, default=str)}"
        )
        try:
            response = OllamaClient(self.settings).chat(
                [
                    {"role": "system", "content": "Chỉ trả lời bằng tiếng Việt, ngắn gọn, grounded theo facts."},
                    {"role": "user", "content": prompt},
                ]
            )
            text = self._clean_llm_text(response.text)
            if text:
                return text, True
        except Exception:
            pass
        return self._deterministic_commentary(purpose, facts), False

    def _clean_llm_text(self, value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"```(?:json)?|```", "", text).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:4])

    def _deterministic_commentary(self, purpose: str, facts: dict[str, Any]) -> str:
        if purpose == "chart_insights":
            highest = facts.get("highest_date")
            value = facts.get("highest_value_hours")
            return f"- Ngày cao nhất là {highest} với {self._num_vi(value)} giờ downtime.\n- Cần ưu tiên xem drill-down theo máy trong ngày này."
        if purpose == "multi_source_commentary":
            return "- Downtime và nhóm tổn thất được đối chiếu trong cùng một ngày.\n- Nên dùng kết quả này như tín hiệu ưu tiên điều tra, chưa xem là quan hệ nhân quả."
        if purpose == "management_commentary":
            return "- Ngày được chọn có thể xem là trọng tâm để rà soát vận hành.\n- Cần kết hợp downtime, nhóm tổn thất và OEE tích lũy trước khi kết luận."
        return "- Báo cáo đã tổng hợp các facts chính từ những artifact phân tích trước đó.\n- Các giới hạn phân tích được giữ rõ để tránh diễn giải vượt quá dữ liệu."

    def _date_vi(self, value: date | None) -> str:
        if value is None:
            return ""
        return value.strftime("%d/%m/%Y")

    def _num_vi(self, value: Any) -> str:
        try:
            number = float(value)
        except Exception:
            return str(value)
        if number.is_integer():
            return f"{int(number):,}".replace(",", ".")
        return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _timezone_error(self, question: str, route: SourceRoute) -> str | None:
        text = normalize_text(question)
        needs_business_day = route.time_semantics in {"as_of", "period", "trend"} or any(term in text for term in ["ngay", "thang", "ca", "day", "month", "shift"])
        if not needs_business_day:
            return None
        if not self.settings.business_timezone:
            return "BUSINESS_TIMEZONE is not configured, so day, month, shift, and as-of boundaries are locked."
        try:
            ZoneInfo(self.settings.business_timezone)
        except ZoneInfoNotFoundError:
            return f"BUSINESS_TIMEZONE is invalid: {self.settings.business_timezone}"
        return None

    def _business_zone(self) -> ZoneInfo:
        if not self.settings.business_timezone:
            raise ValueError("BUSINESS_TIMEZONE is required.")
        return ZoneInfo(self.settings.business_timezone)

    def _resolve_time_window(self, question: str, source_id: str) -> TimeWindow:
        local_tz = self._business_zone() if self.settings.business_timezone else None
        text = normalize_text(question)
        explicit = self._explicit_date(question)
        if explicit and local_tz:
            if any(term in text for term in ["tu dau thang", "dau thang", "month to date", "mtd"]):
                start_date = explicit.replace(day=1)
            else:
                start_date = explicit
            start = datetime.combine(start_date, time.min, tzinfo=local_tz)
            end = start + timedelta(days=1)
            if start_date != explicit:
                end = datetime.combine(explicit, time.min, tzinfo=local_tz) + timedelta(days=1)
            return TimeWindow(start=start, end=end, label=explicit.isoformat(), resolution="explicit_date")
        day_only = self._day_only(question)
        if day_only and local_tz:
            inferred = self._latest_matching_day(source_id, day_only, local_tz)
            if inferred:
                start = datetime.combine(inferred, time.min, tzinfo=local_tz)
                end = start + timedelta(days=1)
                return TimeWindow(start=start, end=end, label=inferred.isoformat(), resolution="latest_matching_day")
        return TimeWindow(start=None, end=None, label="full available range", resolution="full_range")

    def _explicit_date(self, question: str) -> date | None:
        for pattern in [r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"]:
            match = re.search(pattern, question)
            if not match:
                continue
            if pattern.startswith("\\b(\\d{4})"):
                year, month, day = [int(part) for part in match.groups()]
            else:
                day, month, year = [int(part) for part in match.groups()]
            return date(year, month, day)
        return None

    def _day_only(self, question: str) -> int | None:
        text = normalize_text(question)
        match = re.search(r"\b(?:ngay|day)\s+(\d{1,2})\b", text)
        if not match:
            return None
        day = int(match.group(1))
        return day if 1 <= day <= 31 else None

    def _latest_matching_day(self, source_id: str, day: int, local_tz: ZoneInfo) -> date | None:
        source = self.registry.by_id()[source_id]
        if source_id == "apqoee_cumulative":
            df = pd.read_excel(source.workbook_path, sheet_name=0, usecols=["ExecuteAt"])
            times = pd.to_datetime(df["ExecuteAt"], utc=True, errors="coerce").dropna().dt.tz_convert(local_tz)
            dates = sorted({ts.date() for ts in times if ts.day == day})
            return dates[-1] if dates else None
        df = self._load_event_workbook(source.workbook_path)
        dates = sorted({ts.date() for ts in df["start_time"].dropna() if ts.day == day})
        return dates[-1] if dates else None

    def _plan_end(self, plan: ExecutionPlan, default_end: datetime) -> datetime:
        raw = plan.time_scope.get("end")
        if raw:
            return datetime.fromisoformat(str(raw))
        return default_end

    def _event_window(self, plan: ExecutionPlan, df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
        start_raw = plan.time_scope.get("start")
        end_raw = plan.time_scope.get("end")
        if start_raw and end_raw:
            return pd.Timestamp(datetime.fromisoformat(str(start_raw)).replace(tzinfo=None)), pd.Timestamp(datetime.fromisoformat(str(end_raw)).replace(tzinfo=None))
        return pd.Timestamp(df["start_time"].min()), pd.Timestamp(df["end_time"].max())

    def _window_dict(self, window: TimeWindow) -> dict[str, Any]:
        return {
            "start": window.start.isoformat() if window.start else None,
            "end": window.end.isoformat() if window.end else None,
            "label": window.label,
            "resolution": window.resolution,
            "business_timezone": self.settings.business_timezone or None,
        }

    def _combined_time_scope(self, rows: list[dict[str, Any]], plans: list[ExecutionPlan]) -> dict[str, Any]:
        labels = [plan.time_scope.get("label") for plan in plans if plan.time_scope.get("label")]
        return {
            "label": ", ".join(dict.fromkeys(str(label) for label in labels)) if labels else "not specified",
            "business_timezone": self.settings.business_timezone or None,
            "per_source": {plan.source_id: plan.time_scope for plan in plans},
        }

    def _is_period_specific_oee(self, text: str) -> bool:
        return "oee" in text and any(term in text for term in ["rieng ngay", "trong ngay", "period", "daily", "ngay"]) and not any(term in text for term in ["tich luy", "cumulative", "den ngay", "as of"])


class UnsupportedCalculation(ValueError):
    pass


def _artifact_created_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    created = meta.get("artifact_created") if isinstance(meta, dict) else None
    if isinstance(created, dict):
        return created
    trace = meta.get("production_turn_trace") if isinstance(meta, dict) and isinstance(meta.get("production_turn_trace"), dict) else {}
    created = trace.get("artifact_created") if isinstance(trace, dict) else None
    return created if isinstance(created, dict) else None


def _row_get(row: dict[str, Any], *keys: str) -> Any:
    normalized = {normalize_text(str(key)): value for key, value in row.items()}
    for key in keys:
        if key in row:
            return row[key]
        value = normalized.get(normalize_text(key))
        if value is not None:
            return value
    return None


def _split_value_unit(value: Any, unit: Any = None) -> tuple[Any, str | None]:
    if unit:
        return value, str(unit)
    if not isinstance(value, str):
        return value, None
    text = value.strip()
    if text.endswith("%"):
        return text[:-1].strip(), "%"
    for suffix in ["giờ/lần", "giờ", "lần", "máy", "hours"]:
        marker = f" {suffix}"
        if text.endswith(marker):
            return text[: -len(marker)].strip(), suffix
    return value, None


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        text = str(line or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
