from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import pandas as pd

from scripts_ingest import main as run_ingest
from src.application.schemas import (
    ActiveFilePayload,
    ArtifactPayload,
    ChartPayload,
    ChatResponse,
    ConversationDetail,
    ConversationMessage,
    ConversationPayload,
    DashboardPayload,
    DataStatus,
    DownloadPayload,
    FilterPayload,
    HealthStatus,
    SourcePayload,
    TablePayload,
)
from src.catalog.profiler import build_catalog, load_catalog
from src.conversation.clarification import ClarificationResolver, build_plan_from_resolved_message, restore_topic_plan
from src.config import Settings, get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.application.customer_intents import CustomerIntentResult, detect_customer_intent
from src.application.row_level import try_row_level_response
from src.application.grounding import (
    GroundedComposerValidator,
    build_fact_registry_from_table,
    build_open_ended_answer_brief,
    brief_to_prompt_payload,
    deterministic_open_ended_answer,
    deterministic_table_commentary,
    json_payload,
)
from src.application.turn_contracts import (
    ChartContract,
    RequestContract,
    build_request_contract,
    coverage_for_plan,
    new_lineage,
)
from src.files.lifecycle import FileLifecycleService
from src.files.upload_store import find_uploaded_file, list_uploaded_files
from src.ingestion.cache_manager import ParquetCache
from src.llm.ollama_client import OllamaClient
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor
from src.query.schemas import MetricSpec, QueryPlan
from src.query_understanding.deterministic_planner import DeterministicPlanner
from src.rendering.chart_renderer import build_chart
from src.rendering.dashboard import kpi_cards
from src.rendering.formatters import format_dataframe_for_display, format_duration, format_vn_number, humanize_column_name
from src.rendering.presentation import PresentedResponse, build_presented_response
from src.rendering.report_exporter import export_excel_result, export_html_report


class ChatApplicationService:
    def __init__(
        self,
        settings: Settings | None = None,
        memory_service: ConversationMemoryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.memory_service = memory_service or ConversationMemoryService(
            db_path=self.settings.memory_db_path,
            cache_root=self.settings.cache_dir,
            enabled=self.settings.enable_persistent_memory,
            recent_turns_limit=self.settings.recent_turns_limit,
        )
        self._catalog: dict | None = None

    def get_catalog(self, force: bool = False) -> dict:
        if force or self._catalog is None:
            if force or not (self.settings.cache_dir / "data_catalog.json").exists():
                self._catalog = run_ingest(force=force)
            else:
                self._catalog = load_catalog(self.settings.cache_dir)
        return self._catalog

    def reload_catalog_from_cache(self) -> dict:
        if (self.settings.cache_dir / "data_catalog.json").exists():
            self._catalog = load_catalog(self.settings.cache_dir)
        else:
            cache = ParquetCache(self.settings.cache_dir)
            self._catalog = build_catalog(cache.load_tables(), self.settings.cache_dir)
        return self._catalog

    def get_catalog_for_file(self, file_id: str) -> dict:
        catalog = self.get_catalog()
        record = find_uploaded_file(file_id)
        if not record:
            return {**catalog, "tables": []}
        filename = str(record.get("filename") or "")
        exact_tables = [
            table
            for table in catalog.get("tables", [])
            if _table_file_id(table) == file_id
        ]
        tables = exact_tables or [
            table
            for table in catalog.get("tables", [])
            if _table_source_filename(table).lower() == filename.lower()
        ]
        if not tables:
            catalog = self.reload_catalog_from_cache()
            exact_tables = [
                table
                for table in catalog.get("tables", [])
                if _table_file_id(table) == file_id
            ]
            tables = exact_tables or [
                table
                for table in catalog.get("tables", [])
                if _table_source_filename(table).lower() == filename.lower()
            ]
        return {**catalog, "tables": tables}

    def reload_data(self) -> DataStatus:
        catalog = self.get_catalog(force=True)
        return self.data_status(catalog)

    def data_status(self, catalog: dict | None = None) -> DataStatus:
        catalog = catalog or self.get_catalog()
        tables = [
            {
                "name": _readable_table_name(table),
                "row_count": int(table.get("row_count") or 0),
            }
            for table in catalog.get("tables", [])
        ]
        return DataStatus(catalog_available=bool(catalog.get("tables")), table_count=len(tables), tables=tables)

    def health(self) -> HealthStatus:
        ollama = OllamaClient(self.settings).health()
        snapshot = self.memory_service.snapshot()
        memory_available = not bool(snapshot.get("persistence_degraded"))
        return HealthStatus(
            status="ok" if memory_available else "degraded",
            ollama_available=bool(ollama.get("ok")),
            model=self.settings.ollama_model,
            database_available=bool((self.settings.cache_dir / "data_catalog.json").exists()),
            memory_available=memory_available,
        )

    def create_conversation(self, title: str | None = None) -> ConversationPayload:
        state = self.memory_service.create_conversation(title=title)
        record = self.memory_service.get_conversation(state.conversation_id)
        return _conversation_payload(record or {"id": state.conversation_id, "title": title or "Cuộc trò chuyện", "created_at": "", "updated_at": "", "status": "active"})

    def list_conversations(self) -> list[ConversationPayload]:
        return [_conversation_payload(item) for item in self.memory_service.list_conversations()]

    def get_conversation(self, conversation_id: str, limit: int = 200) -> ConversationDetail | None:
        record = self.memory_service.get_conversation(conversation_id)
        if not record or record.get("status") == "deleted":
            return None
        turns = self.memory_service.load_recent_turns(conversation_id, limit)
        return ConversationDetail(
            **_conversation_payload(record).model_dump(),
            messages=[
                ConversationMessage(
                    id=row.get("id"),
                    role=row.get("role", "assistant"),
                    content=row.get("content", ""),
                    created_at=row.get("created_at"),
                    execution_mode=row.get("execution_mode"),
                    response=_stored_chat_response(row.get("response_json")),
                )
                for row in turns
            ],
        )

    def update_conversation(self, conversation_id: str, title: str) -> ConversationPayload | None:
        if not self.memory_service.get_conversation(conversation_id):
            return None
        self.memory_service.update_conversation(conversation_id, title=title.strip()[:120])
        record = self.memory_service.get_conversation(conversation_id)
        return _conversation_payload(record) if record else None

    def delete_conversation(self, conversation_id: str) -> None:
        self.memory_service.delete_conversation(conversation_id)

    def reset_context(self, conversation_id: str) -> ConversationDetail | None:
        if not self.memory_service.get_conversation(conversation_id):
            return None
        self.memory_service.reset_conversation(conversation_id)
        return self.get_conversation(conversation_id)

    def create_conversation(self, title: str | None = None, source_file_id: str | None = None) -> ConversationPayload:
        file_record = self._validate_ready_file(source_file_id) if source_file_id else None
        state = self.memory_service.create_conversation(
            title=title,
            source_file_id=str(file_record.get("id")) if file_record else None,
            source_file_name=str(file_record.get("filename")) if file_record else None,
            source_file_sha256=str(file_record.get("sha256") or "") if file_record and file_record.get("sha256") else None,
            source_catalog_version=str(file_record.get("catalog_version") or "") if file_record and file_record.get("catalog_version") else None,
        )
        record = self.memory_service.get_conversation(state.conversation_id)
        return _conversation_payload(
            record or {"id": state.conversation_id, "title": title or "Cuoc tro chuyen", "created_at": "", "updated_at": "", "status": "active"},
            state,
        )

    def list_conversations(self) -> list[ConversationPayload]:
        payloads = []
        for item in self.memory_service.list_conversations():
            state = self.memory_service.load_conversation(str(item.get("id", "")))
            self._backfill_source_from_state(item, state)
            payloads.append(_conversation_payload(item, state))
        return payloads

    def get_conversation(self, conversation_id: str, limit: int = 200) -> ConversationDetail | None:
        record = self.memory_service.get_conversation(conversation_id)
        if not record or record.get("status") == "deleted":
            return None
        state = self.memory_service.load_conversation(conversation_id)
        self._backfill_source_from_state(record, state)
        self._sync_state_to_conversation_source(record, state)
        turns = self.memory_service.load_recent_turns(conversation_id, limit)
        return ConversationDetail(
            **_conversation_payload(record, state).model_dump(),
            messages=[
                ConversationMessage(
                    id=row.get("id"),
                    role=row.get("role", "assistant"),
                    content=row.get("content", ""),
                    created_at=row.get("created_at"),
                    execution_mode=row.get("execution_mode"),
                    response=_stored_chat_response(row.get("response_json")),
                )
                for row in turns
            ],
        )

    def update_conversation(self, conversation_id: str, title: str) -> ConversationPayload | None:
        if not self.memory_service.get_conversation(conversation_id):
            return None
        self.memory_service.update_conversation(conversation_id, title=title.strip()[:120])
        record = self.memory_service.get_conversation(conversation_id)
        state = self.memory_service.load_conversation(conversation_id)
        return _conversation_payload(record, state) if record else None

    def set_active_file(self, conversation_id: str, file_id: str) -> ActiveFilePayload | None:
        conversation = self.memory_service.get_conversation(conversation_id)
        if not conversation:
            return None
        record = self._validate_ready_file(file_id)
        existing_source = str(conversation.get("source_file_id") or "")
        if existing_source and existing_source != file_id:
            raise ValueError("CONVERSATION_FILE_MISMATCH")
        state = self.memory_service.load_conversation(conversation_id)
        if not existing_source:
            self.memory_service.bind_conversation_source(
                conversation_id,
                source_file_id=str(record.get("id") or ""),
                source_file_name=str(record.get("filename") or ""),
                source_file_sha256=str(record.get("sha256") or "") if record.get("sha256") else None,
                source_catalog_version=str(record.get("catalog_version") or "") if record.get("catalog_version") else None,
            )
        state.active_file_id = existing_source or str(record.get("id") or "")
        state.active_file_name = str(conversation.get("source_file_name") or record.get("filename") or "")
        state.restore_file_context(state.active_file_id)
        self.memory_service.save_state(state)
        return ActiveFilePayload(
            conversation_id=conversation_id,
            active_file_id=state.active_file_id,
            active_file_name=state.active_file_name,
            status="ready",
        )

    def process_message(self, conversation_id: str, message: str, debug: bool = False, source_file_id: str | None = None) -> ChatResponse:
        started = perf_counter()
        message = message.strip()
        catalog = self.get_catalog()
        state = self.memory_service.load_conversation(conversation_id)
        conversation = self.memory_service.get_conversation(conversation_id)
        if not conversation:
            state = self.memory_service.create_conversation()
            conversation_id = state.conversation_id
            conversation = self.memory_service.get_conversation(conversation_id) or {}
        self._backfill_source_from_state(conversation, state)
        conversation_source_id = str(conversation.get("source_file_id") or state.active_file_id or "")
        if source_file_id and conversation_source_id and source_file_id != conversation_source_id:
            raise ValueError("CONVERSATION_FILE_MISMATCH")
        if source_file_id and not conversation_source_id:
            file_record = self._validate_ready_file(source_file_id)
            self.memory_service.bind_conversation_source(
                conversation_id,
                source_file_id=str(file_record.get("id") or ""),
                source_file_name=str(file_record.get("filename") or ""),
                source_file_sha256=str(file_record.get("sha256") or "") if file_record.get("sha256") else None,
                source_catalog_version=str(file_record.get("catalog_version") or "") if file_record.get("catalog_version") else None,
            )
            conversation = self.memory_service.get_conversation(conversation_id) or conversation
        self._sync_state_to_conversation_source(conversation, state)

        self._set_title_from_first_message(conversation_id, message)
        self.memory_service.save_turn(state, role="user", content=message)

        customer_intent = detect_customer_intent(message)
        metadata_response = self._try_metadata_response(conversation_id, message, customer_intent, catalog, debug, started)
        if metadata_response is not None:
            self._save_assistant_response(
                state,
                metadata_response,
                content=metadata_response.summary or metadata_response.title,
                execution_mode=metadata_response.metadata.get("execution_mode"),
                query_plan=None,
                result_summary=None,
            )
            return metadata_response

        result = None
        html_path: Path | None = None
        xlsx_path: Path | None = None
        timings: dict[str, Any] = {}

        try:
            planner = QueryPlanner(catalog, self.settings)
            planned = planner.plan(message, state)
            plan = planned.plan
            metadata = dict(planned.metadata or {})
            metadata["persistence_degraded"] = self.memory_service.persistence_degraded

            if plan.intent in {"clarification", "refusal", "safe_failure"}:
                presented = build_presented_response(message, plan, pd.DataFrame(), catalog, [])
            else:
                query_started = perf_counter()
                result = SafeQueryExecutor(catalog).execute(plan)
                timings["query_latency_ms"] = round(result.latency_ms, 1)
                timings["query_wall_ms"] = round((perf_counter() - query_started) * 1000, 1)
                chart = build_chart(result.dataframe, plan, catalog)
                sources = self._sources_for_plan(plan, catalog)
                presented = build_presented_response(message, plan, result.dataframe, catalog, sources, chart)
                export_summary = " ".join(part for part in [presented.title, presented.primary_value, presented.summary] if part)
                if plan.intent == "report" or plan.output == "report":
                    html_path = export_html_report(message, export_summary, result.dataframe, plan, sources, self.settings.reports_dir)
                    xlsx_path = export_excel_result(message, export_summary, result.dataframe, sources, self.settings.reports_dir)
                state.update_from_plan(plan, plan.output)
                state.update_from_result(result.dataframe)

            metadata.setdefault("latency_ms", {})
            if isinstance(metadata["latency_ms"], dict):
                metadata["latency_ms"]["total"] = round((perf_counter() - started) * 1000, 1)
                metadata["latency_ms"].update(timings)
            metadata["debug"] = self._debug_payload(debug, planned.plan, result.sql if result else None, state)

            response = self._response_from_presented(
                conversation_id=conversation_id,
                presented=presented,
                plan=plan,
                raw_dataframe=result.dataframe if result else None,
                catalog=catalog,
                metadata=metadata,
                html_path=html_path,
                xlsx_path=xlsx_path,
            )
            assistant_content = response.primary_value or response.summary or response.title
            self.memory_service.save_turn(
                state,
                role="assistant",
                content=assistant_content,
                execution_mode=metadata.get("execution_mode") or metadata.get("mode"),
                query_plan=plan.model_dump(),
                result_summary=state.last_result_summary,
                result_dataframe=result.dataframe if result is not None else None,
            )
            return response
        except Exception as exc:
            response = ChatResponse(
                message_id=str(uuid4()),
                conversation_id=conversation_id,
                response_type="error",
                title="Không thể hoàn tất",
                summary="Không thể kết nối với hệ thống xử lý." if not debug else str(exc),
                metadata={"latency_ms": {"total": round((perf_counter() - started) * 1000, 1)}},
            )
            self.memory_service.save_turn(state, role="assistant", content=response.summary, execution_mode="ERROR")
            return response

    def process_message(self, conversation_id: str, message: str, debug: bool = False, source_file_id: str | None = None) -> ChatResponse:
        started = perf_counter()
        message = message.strip()
        state = self.memory_service.load_conversation(conversation_id)
        conversation = self.memory_service.get_conversation(conversation_id)
        if not conversation:
            state = self.memory_service.create_conversation()
            conversation_id = state.conversation_id
            conversation = self.memory_service.get_conversation(conversation_id) or {}
        self._backfill_source_from_state(conversation, state)
        conversation_source_id = str(conversation.get("source_file_id") or state.active_file_id or "")
        if source_file_id and conversation_source_id and source_file_id != conversation_source_id:
            raise ValueError("CONVERSATION_FILE_MISMATCH")
        if source_file_id and not conversation_source_id:
            file_record = self._validate_ready_file(source_file_id)
            self.memory_service.bind_conversation_source(
                conversation_id,
                source_file_id=str(file_record.get("id") or ""),
                source_file_name=str(file_record.get("filename") or ""),
                source_file_sha256=str(file_record.get("sha256") or "") if file_record.get("sha256") else None,
                source_catalog_version=str(file_record.get("catalog_version") or "") if file_record.get("catalog_version") else None,
            )
            conversation = self.memory_service.get_conversation(conversation_id) or conversation
        self._sync_state_to_conversation_source(conversation, state)

        self._set_title_from_first_message(conversation_id, message)
        self.memory_service.save_turn(state, role="user", content=message)

        preflight = self._preflight_file_scope(conversation_id, state, message, debug, started)
        if preflight is not None:
            self._save_assistant_response(state, preflight)
            return preflight

        catalog = self.get_catalog_for_file(state.active_file_id or "")
        if not catalog.get("tables"):
            response = self._file_scope_response(
                conversation_id,
                "error",
                "Source file is not queryable",
                "The selected Excel file does not have queryable tables in the catalog. Reload the data or start a new chat with another Ready file.",
                "SAFE_FAILURE",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
            self._save_assistant_response(state, response, execution_mode="SAFE_FAILURE")
            return response

        request_contract = build_request_contract(message, state.active_file_id, bool(state.last_result_summary or state.last_result_cache_id))
        lineage = new_lineage(conversation_id, state.active_file_id)
        contract_metadata = {
            "lineage": lineage,
            "request_contract": request_contract.model_dump(),
            "request_contract_id": lineage["request_contract_id"],
            "query_plan_id": lineage["query_plan_id"],
            "query_result_id": lineage["query_result_id"],
            "answer_brief_id": lineage["answer_brief_id"],
            "chart_spec_id": lineage["chart_spec_id"],
            "report_artifact_id": lineage["report_artifact_id"],
        }
        planning_state = state
        if request_contract.relation_to_previous_turn == "NEW_REQUEST" and state.pending_clarification is None:
            planning_state = state.model_copy(deep=True)
            planning_state.clear_analysis_context()
            planning_state.active_file_id = state.active_file_id
            planning_state.active_file_name = state.active_file_name

        customer_intent = detect_customer_intent(message)
        if customer_intent.intent in {"REFUSAL", "SAFE_FAILURE"}:
            metadata_response = self._try_metadata_response(conversation_id, message, customer_intent, catalog, debug, started)
            if metadata_response is not None:
                self._attach_file_scope_metadata(metadata_response, state, True)
                metadata_response.metadata.update(contract_metadata)
                self._save_assistant_response(state, metadata_response, query_plan=None, result_summary=None)
                return metadata_response

        report_response = self._try_report_orchestration_response(
            conversation_id, message, catalog, state, request_contract, lineage, debug, started
        )
        if report_response is not None:
            report_response.metadata.update(contract_metadata)
            self._save_assistant_response(state, report_response)
            return report_response

        open_ended_response = self._try_open_ended_analysis_response(conversation_id, message, catalog, planning_state, debug, started)
        if open_ended_response is not None:
            open_ended_response.metadata.update(contract_metadata)
            self._save_assistant_response(state, open_ended_response)
            return open_ended_response

        clarification = ClarificationResolver(catalog).resolve_pending(
            conversation_id,
            message,
            planning_state,
            debug=debug,
            started=started,
        )
        if clarification.response is not None:
            state.pending_clarification = planning_state.pending_clarification
            state.resolved_request = planning_state.resolved_request
            clarification.response.metadata.update(contract_metadata)
            self._save_assistant_response(state, clarification.response)
            return clarification.response
        if clarification.resolved_message:
            state.pending_clarification = planning_state.pending_clarification
            state.resolved_request = planning_state.resolved_request
            message = clarification.resolved_message
        forced_plan = build_plan_from_resolved_message(catalog, planning_state, message) if clarification.resolved_message else None
        if forced_plan is None and request_contract.relation_to_previous_turn != "NEW_REQUEST":
            forced_plan = restore_topic_plan(catalog, state, message)
        if forced_plan is None and state.pending_clarification is None and _starts_slot_clarification(message):
            started_clarification = ClarificationResolver(catalog).maybe_start(
                conversation_id,
                message,
                planning_state,
                QueryPlan(intent="clarification", output="text", clarification_question="Cần làm rõ yêu cầu."),
                debug=debug,
                started=started,
            )
            if started_clarification is not None:
                state.pending_clarification = planning_state.pending_clarification
                state.resolved_request = planning_state.resolved_request
                started_clarification.metadata.update(contract_metadata)
                self._save_assistant_response(state, started_clarification)
                return started_clarification

        if request_contract.relation_to_previous_turn == "FOLLOW_UP_ON_PREVIOUS_RESULT":
            semantic_followup = self._try_semantic_followup_response(conversation_id, message, state, debug, started)
            if semantic_followup is not None:
                semantic_followup.metadata.update(contract_metadata)
                self._save_assistant_response(state, semantic_followup)
                return semantic_followup

        row_response = try_row_level_response(conversation_id, message, catalog, planning_state, debug, started)
        if row_response is not None:
            row_response.metadata.update(contract_metadata)
            self._save_assistant_response(state, row_response, query_plan=None, result_summary=None)
            return row_response

        metadata_response = self._try_metadata_response(conversation_id, message, customer_intent, catalog, debug, started)
        if metadata_response is not None:
            self._attach_file_scope_metadata(metadata_response, state, True)
            metadata_response.metadata.update(contract_metadata)
            self._save_assistant_response(state, metadata_response, query_plan=None, result_summary=None)
            return metadata_response

        result = None
        html_path: Path | None = None
        xlsx_path: Path | None = None
        timings: dict[str, Any] = {}

        try:
            if forced_plan is not None:
                plan = forced_plan
                metadata = {
                    "execution_mode": "DETERMINISTIC",
                    "router_confidence": 1.0,
                    "routing_reason": "pending_clarification_resolved",
                    "llm_called": False,
                    "llm_call_count": 0,
                    "clarification_resolution": "COMPLETE",
                    "selected_tables": forced_plan.tables,
                }
            else:
                planner = QueryPlanner(catalog, self.settings)
                planned = planner.plan(message, planning_state)
                plan = planned.plan
                metadata = dict(planned.metadata or {})
            metadata["persistence_degraded"] = self.memory_service.persistence_degraded
            self._attach_file_scope_to_metadata(metadata, state, True)
            metadata.update(contract_metadata)

            if not self._plan_within_file_scope(plan, catalog):
                metadata["execution_mode"] = "SAFE_FAILURE"
                metadata["file_scope_validated"] = False
                allowed = {table["table_name"] for table in catalog.get("tables", [])}
                metadata["file_scope_violation"] = sorted(set(plan.tables) - allowed)
                plan = QueryPlan(
                    intent="safe_failure",
                    output="text",
                    clarification_question="Unable to build a safe query within the selected Excel file.",
                )
            if plan.intent not in {"clarification", "refusal", "safe_failure"}:
                if request_contract.intent == "chart":
                    current_coverage = coverage_for_plan(request_contract, plan)
                    if current_coverage.missing:
                        deterministic_repair = DeterministicPlanner(catalog, self.settings).parse(message, planning_state)
                        if deterministic_repair.plan is not None:
                            repair_coverage = coverage_for_plan(request_contract, deterministic_repair.plan)
                            if not repair_coverage.missing:
                                plan = deterministic_repair.plan
                                metadata["deterministic_repair_applied"] = True
                                metadata["deterministic_repair_reason"] = deterministic_repair.reason
                coverage = coverage_for_plan(request_contract, plan)
                metadata["request_coverage"] = coverage.model_dump()
                if request_contract.intent in {"chart", "report"} and coverage.missing:
                    metadata["execution_mode"] = "SAFE_FAILURE"
                    metadata["coverage_gate_failed"] = True
                    plan = QueryPlan(
                        intent="safe_failure",
                        output="text",
                        clarification_question="Unable to build a chart/report that matches the requested dimensions, metrics, and output.",
                    )

            if plan.intent in {"clarification", "refusal", "safe_failure"}:
                started_clarification = ClarificationResolver(catalog).maybe_start(
                    conversation_id,
                    message,
                    state,
                    plan,
                    debug=debug,
                    started=started,
                )
                if started_clarification is not None:
                    metadata.update(started_clarification.metadata)
                    self._save_assistant_response(state, started_clarification, plan=plan, query_plan=plan.model_dump())
                    return started_clarification
                presented = build_presented_response(message, plan, pd.DataFrame(), catalog, [])
            else:
                query_started = perf_counter()
                result = SafeQueryExecutor(catalog).execute(plan)
                timings["query_latency_ms"] = round(result.latency_ms, 1)
                timings["query_wall_ms"] = round((perf_counter() - query_started) * 1000, 1)
                chart = build_chart(result.dataframe, plan, catalog)
                sources = self._sources_for_plan(plan, catalog)
                presented = build_presented_response(message, plan, result.dataframe, catalog, sources, chart)
                export_summary = " ".join(part for part in [presented.title, presented.primary_value, presented.summary] if part)
                if plan.intent == "report" or plan.output == "report":
                    html_path = export_html_report(message, export_summary, result.dataframe, plan, sources, self.settings.reports_dir)
                    xlsx_path = export_excel_result(message, export_summary, result.dataframe, sources, self.settings.reports_dir)
                state.update_from_plan(plan, plan.output)
                state.update_from_result(result.dataframe)
                state.remember_topic(plan)

            metadata.setdefault("latency_ms", {})
            if isinstance(metadata["latency_ms"], dict):
                metadata["latency_ms"]["total"] = round((perf_counter() - started) * 1000, 1)
                metadata["latency_ms"].update(timings)
            metadata["debug"] = self._debug_payload(debug, plan, result.sql if result else None, state)
            if isinstance(metadata.get("debug"), dict):
                metadata["debug"]["scoped_catalog_tables"] = [table.get("table_name") for table in catalog.get("tables", [])]

            response = self._response_from_presented(
                conversation_id=conversation_id,
                presented=presented,
                plan=plan,
                raw_dataframe=result.dataframe if result else None,
                catalog=catalog,
                metadata=metadata,
                html_path=html_path,
                xlsx_path=xlsx_path,
            )
            if (
                result is not None
                and not result.dataframe.empty
                and _requests_commentary(_ascii_text(message))
                and response.response_type in {"table", "chart", "scalar", "dashboard", "report"}
            ):
                commentary = self._generate_grounded_commentary(message, state, response)
                if commentary:
                    response.summary = f"{response.summary}\n\n{commentary}".strip() if response.summary else commentary
                    response.metadata["commentary_attached"] = True
                    response.metadata["grounded_composer_called"] = True
                    response.metadata["llm_called"] = True
                    response.metadata["llm_call_count"] = int(response.metadata.get("llm_call_count") or 0) + 1
                    response.metadata["composer_model"] = self.settings.ollama_model
            assistant_content = response.primary_value or response.summary or response.title
            self._save_assistant_response(
                state,
                response,
                content=assistant_content,
                execution_mode=metadata.get("execution_mode") or metadata.get("mode"),
                plan=plan,
                query_plan=plan.model_dump(),
                result_summary=state.last_result_summary,
                result_dataframe=result.dataframe if result is not None else None,
            )
            return response
        except Exception as exc:
            response = ChatResponse(
                message_id=str(uuid4()),
                conversation_id=conversation_id,
                response_type="error",
                title="Unable to complete the request",
                summary="The analysis service could not complete this request." if not debug else str(exc),
                metadata={
                    "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
                    "active_file_id": state.active_file_id,
                    "active_file_name": state.active_file_name,
                    "file_scope_validated": False,
                },
            )
            self._save_assistant_response(state, response, content=response.summary, execution_mode="ERROR")
            return response

    def _preflight_file_scope(self, conversation_id: str, state, message: str, debug: bool, started: float) -> ChatResponse | None:
        if not state.active_file_id:
            return self._file_scope_response(
                conversation_id,
                "clarification",
                "No Excel file selected",
                "Please select a Ready Excel file before asking data questions.",
                "CLARIFICATION",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        record = find_uploaded_file(state.active_file_id)
        if not record:
            return self._file_scope_response(
                conversation_id,
                "error",
                "Source file is unavailable",
                "The source file for this conversation is no longer available. Select another file to start a new chat.",
                "SAFE_FAILURE",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        state.active_file_name = str(record.get("filename") or state.active_file_name or "")
        if record.get("status") != "ready" or not record.get("queryable"):
            status = str(record.get("status") or "")
            summary = (
                "The selected Excel file is still processing. Please wait until it is Ready before asking data questions."
                if status in {"uploaded", "uploading", "processing"}
                else "The selected Excel file is not queryable. Please re-upload it or start a new chat with another Ready file."
            )
            return self._file_scope_response(
                conversation_id,
                "error",
                "Excel file is not ready",
                summary,
                "SAFE_FAILURE",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        other = self._mentioned_other_file(message, state.active_file_id)
        if other:
            return self._file_scope_response(
                conversation_id,
                "refusal",
                "Different source file requested",
                f"This conversation is bound to {state.active_file_name}. Start a new chat to ask questions about {other}.",
                "REFUSAL",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        return None

    def _validate_ready_file(self, file_id: str | None) -> dict[str, Any]:
        if not file_id:
            raise ValueError("File not found")
        record = find_uploaded_file(file_id)
        if not record:
            raise ValueError("File not found")
        if record.get("status") != "ready" or not record.get("queryable"):
            raise ValueError("File is not ready")
        catalog = self.get_catalog()
        if not any(_table_file_id(table) == file_id for table in catalog.get("tables", [])):
            catalog = self.reload_catalog_from_cache()
        readiness = FileLifecycleService(self.settings).validate_readiness(file_id, catalog=catalog)
        if not readiness.get("ok"):
            raise ValueError(str(readiness.get("message") or "File is not queryable"))
        return record

    def _backfill_source_from_state(self, record: dict[str, Any], state) -> None:
        if record.get("source_file_id") or not getattr(state, "active_file_id", None):
            return
        try:
            self.memory_service.bind_conversation_source(
                str(record.get("id") or state.conversation_id),
                source_file_id=str(state.active_file_id),
                source_file_name=str(state.active_file_name or ""),
            )
            record["source_file_id"] = state.active_file_id
            record["source_file_name"] = state.active_file_name
        except ValueError:
            pass

    def _sync_state_to_conversation_source(self, record: dict[str, Any], state) -> None:
        source_file_id = str(record.get("source_file_id") or "")
        if not source_file_id:
            return
        source_file_name = str(record.get("source_file_name") or state.active_file_name or "")
        file_changed = bool(state.active_file_id) and state.active_file_id != source_file_id
        if file_changed:
            # Switching to a different workbook: preserve the previous file's analysis
            # context, then restore (or start fresh on) the new file's context.
            state.save_file_context()
            state.active_file_id = source_file_id
            state.active_file_name = source_file_name
            state.restore_file_context(source_file_id)
            self.memory_service.save_state(state)
        else:
            # Same workbook (or first bind): keep the live analysis context
            # (last_plan, topic_frames, dimensions) so follow-up turns can merge.
            state.active_file_id = source_file_id
            state.active_file_name = source_file_name

    def _mentioned_other_file(self, message: str, active_file_id: str) -> str | None:
        normalized = _ascii_text(message)
        aliases = {
            "EntryTransaction": ["entrytransaction", "entry transaction", "entry_transaction", "file entrytransaction"],
            "Loss_Assignment": ["loss assignment", "loss_assignment", "file loss assignment"],
            "Machine_Downtime": ["machine downtime", "machine_downtime", "file machine downtime"],
        }
        active = find_uploaded_file(active_file_id) or {}
        active_name = str(active.get("filename") or "")
        active_key = next((key for key in aliases if key.lower() in active_name.lower()), "")
        for record in list_uploaded_files():
            if record.get("id") == active_file_id:
                continue
            filename = str(record.get("filename") or "")
            key = next((item for item in aliases if item.lower() in filename.lower()), "")
            terms = aliases.get(key, []) + [_ascii_text(Path(filename).stem)]
            if key and key != active_key and any(term and term in normalized for term in terms):
                return filename
        return None

    def _try_report_orchestration_response(
        self,
        conversation_id: str,
        message: str,
        catalog: dict,
        state,
        request_contract: RequestContract,
        lineage: dict[str, str | None],
        debug: bool,
        started: float,
    ) -> ChatResponse | None:
        if request_contract.intent != "report":
            return None
        table = catalog.get("tables", [None])[0]
        if not table:
            return None
        path = table.get("parquet_path")
        if not path:
            return None
        df = pd.read_parquet(path)
        machine = _role_column(table, "machine") or "may"
        duration = _role_column(table, "duration_seconds") or "duration_seconds"
        start_time = _role_column(table, "start_time")
        loss_name = _role_column(table, "loss_name")
        sections: dict[str, dict[str, Any]] = {}
        report_kind = "downtime" if any(item in request_contract.report_sections for item in ["kpi_total_downtime", "top_machines"]) else "overview"

        record_count = int(len(df))
        total_seconds = float(df[duration].sum()) if duration in df.columns else 0.0
        total_hours = round(total_seconds / 3600, 2)
        date_range = None
        if start_time and start_time in df.columns:
            times = pd.to_datetime(df[start_time], errors="coerce").dropna()
            if not times.empty:
                date_range = {"from": str(times.min().date()), "to": str(times.max().date())}
        sections["dataset_overview"] = {"status": "SUCCESS", "record_count": record_count, "date_range": date_range}

        top_machines = pd.DataFrame()
        if machine in df.columns and duration in df.columns:
            top_machines = (
                df.groupby(machine, dropna=False)
                .agg(total_duration_seconds=(duration, "sum"), row_count=(duration, "size"), avg_duration_seconds=(duration, "mean"))
                .reset_index()
                .sort_values("total_duration_seconds", ascending=False)
                .head(5)
            )
            sections["top_machines"] = {"status": "SUCCESS", "rows": int(len(top_machines))}
        else:
            sections["top_machines"] = {"status": "NOT_ENOUGH_DATA"}

        top_causes = pd.DataFrame()
        if loss_name and loss_name in df.columns and duration in df.columns:
            top_causes = (
                df.groupby(loss_name, dropna=False)
                .agg(total_duration_seconds=(duration, "sum"), row_count=(duration, "size"))
                .reset_index()
                .sort_values("total_duration_seconds", ascending=False)
                .head(5)
            )
            sections["top_causes"] = {"status": "SUCCESS", "rows": int(len(top_causes))}
        else:
            sections["top_causes"] = {"status": "NOT_ENOUGH_DATA"}

        trend = pd.DataFrame()
        if start_time and start_time in df.columns and duration in df.columns:
            trend_source = df.copy()
            trend_source[start_time] = pd.to_datetime(trend_source[start_time], errors="coerce")
            trend_source = trend_source.dropna(subset=[start_time])
            trend_source["report_date"] = trend_source[start_time].dt.date.astype(str)
            trend = (
                trend_source.groupby("report_date", dropna=False)
                .agg(total_duration_seconds=(duration, "sum"))
                .reset_index()
                .sort_values("report_date")
            )
            sections["time_trend"] = {"status": "SUCCESS", "rows": int(len(trend))}
        else:
            sections["time_trend"] = {"status": "NOT_ENOUGH_DATA"}

        sections["kpi_total_downtime"] = {"status": "SUCCESS", "hours": total_hours}
        sections["kpi_stop_count"] = {"status": "SUCCESS", "count": record_count}
        sections["management_commentary"] = {"status": "SUCCESS"}
        sections["source_filters_limitations"] = {"status": "SUCCESS", "source": table.get("source")}

        missing = [name for name in request_contract.report_sections if sections.get(name, {}).get("status") not in {"SUCCESS", "NOT_ENOUGH_DATA"}]
        display_table = format_dataframe_for_display(top_machines if not top_machines.empty else top_causes, catalog)
        chart_plan = QueryPlan(
            intent="chart",
            tables=[table["table_name"]],
            dimensions=["report_date"],
            metrics=[MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")],
            output="line",
            time_granularity="day",
            limit=500,
        )
        chart_metadata = {"lineage": lineage}
        chart = _chart_payload(trend, chart_plan, catalog, chart_metadata) if not trend.empty else None
        summary = _report_summary(report_kind, record_count, total_hours, date_range, top_machines, top_causes)
        html_path, xlsx_path = _export_orchestrated_report(
            message=message,
            report_kind=report_kind,
            summary=summary,
            sections=sections,
            top_machines=top_machines,
            top_causes=top_causes,
            trend=trend,
            reports_dir=self.settings.reports_dir,
            artifact_id=str(lineage["report_artifact_id"]),
            catalog=catalog,
        )
        metadata = {
            "execution_mode": "DETERMINISTIC_REPORT",
            "routing_reason": "multi_query_report_orchestration",
            "llm_called": False,
            "llm_call_count": 0,
            "multi_query_execution": True,
            "report_kind": report_kind,
            "report_section_statuses": sections,
            "report_completeness": {"missing": missing, "required": request_contract.report_sections},
            "chart_contract": chart_metadata.get("chart_contract"),
            "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
            "active_file_id": state.active_file_id,
            "active_file_name": state.active_file_name,
            "file_scope_validated": True,
            "debug": {"report_sections": sections} if debug else None,
        }
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="report",
            title="Báo cáo phân tích downtime" if report_kind == "downtime" else "Báo cáo tổng quan",
            summary=summary,
            table=_table_payload(display_table) if not display_table.empty else None,
            chart=chart,
            sources=_source_payloads(self._sources_for_plan(QueryPlan(tables=[table["table_name"]]), catalog)),
            downloads=[_download_payload(path) for path in [html_path, xlsx_path] if path.exists()],
            metadata=_json_safe(metadata),
        )

    def _try_open_ended_analysis_response(
        self,
        conversation_id: str,
        message: str,
        catalog: dict,
        state,
        debug: bool,
        started: float,
    ) -> ChatResponse | None:
        q = _ascii_text(message)
        if not _is_open_ended_dataset_analysis(q):
            return None
        brief = build_open_ended_answer_brief(catalog, state.active_file_name or "")
        if brief is None:
            return None
        fallback_text = deterministic_open_ended_answer(brief)
        facts = list(brief.allowed_numeric_facts)
        if facts:
            fact_type = type(facts[0])
            facts.extend(fact_type(f"section_{idx}", float(idx), str(idx)) for idx in range(1, 4))
        validator = GroundedComposerValidator(facts)
        text = fallback_text
        llm_called = False
        llm_latency = None
        validation_errors: list[str] = []
        try:
            llm_called = True
            llm = OllamaClient(self.settings).chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Bạn là trợ lý phân tích dữ liệu. Trả lời bằng tiếng Việt có dấu, "
                            "chỉ dùng các số trong payload, không nhắc tên file, không nhắc JSON/context/fallback. "
                            "Chỉ diễn đạt các insight đã chọn trong payload; không tự chọn thêm cột, không tạo metric mới, "
                            "không dùng cột kỹ thuật/index/ID làm insight."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Từ payload đã được tính sẵn, hãy nêu các phát hiện đáng chú ý, so sánh ngắn và giới hạn kết luận. "
                            "Mỗi insight phải gồm phát hiện, bằng chứng và ý nghĩa nghiệp vụ. "
                            "Không tạo số mới, không đổi đơn vị, không suy đoán nguyên nhân ngoài dữ liệu. "
                            "Không mô tả completeness 100%, mode của ID/index, hoặc các câu chung chung như "
                            "'mỗi góc nhìn đo một lát cắt khác nhau'.\n"
                            f"Câu hỏi: {message}\nPayload: {json_payload(brief_to_prompt_payload(brief))}"
                        ),
                    },
                ]
            )
            candidate = (llm.text or "").strip()
            llm_latency = round(llm.latency_ms, 1)
            validation = validator.validate(candidate)
            if candidate and validation.passed:
                text = candidate
            else:
                validation_errors = validation.errors
        except Exception as exc:
            validation_errors = [str(exc)]
        final_validation = validator.validate(text)
        payload = brief_to_prompt_payload(brief)
        metadata = {
            "execution_mode": "REAL_LLM" if llm_called and text != fallback_text else "DETERMINISTIC",
            "routing_reason": "open_ended_grounded_answer_brief",
            "llm_called": llm_called,
            "llm_call_count": 1 if llm_called else 0,
            "llm_model": self.settings.ollama_model if llm_called else None,
            "llm_latency_ms": llm_latency,
            "grounded_composer_called": True,
            "composer_validation_passed": final_validation.passed,
            "composer_validation_errors": final_validation.errors,
            "composer_rejected_errors": validation_errors,
            "composer_fallback_used": text == fallback_text and bool(validation_errors),
            "answer_brief": payload,
            "latency_ms": {"total": round((perf_counter() - started) * 1000, 1), "llm": llm_latency},
            "active_file_id": state.active_file_id,
            "active_file_name": state.active_file_name,
            "file_scope_validated": True,
            "debug": {"answer_brief": payload} if debug else None,
        }
        table = TablePayload(columns=list(brief.table_rows[0].keys()), rows=list(brief.table_rows)) if brief.table_rows else None
        source_table = catalog["tables"][0]
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="table" if table else "text",
            title="Phân tích tổng quan",
            summary=text,
            table=table,
            sources=_source_payloads(self._sources_for_plan(QueryPlan(tables=[source_table["table_name"]]), catalog)),
            metadata=_json_safe(metadata),
        )

    def _generate_grounded_commentary(self, message: str, state, response) -> str | None:
        """Generate 1-3 short grounded observations about an analytics result, when the user
        also asked for commentary in the same multi-part request. Returns None on failure."""
        table = response.table.model_dump() if response.table else None
        facts = build_fact_registry_from_table(response.table, requested_top_n=_extract_top_n(_ascii_text(message)))
        fallback = deterministic_table_commentary(message, response)
        if not fallback:
            return None
        validator = GroundedComposerValidator(facts)
        context = {
            "source_file_name": state.active_file_name,
            "headline": response.summary or response.primary_value or response.title,
            "result_summary": state.last_result_summary or {},
            "table_preview": (table or {}).get("rows", [])[:10] if table else None,
            "allowed_numeric_facts": [fact.__dict__ for fact in facts],
        }
        prompt = (
            "Bạn là trợ lý phân tích dữ liệu. Dựa CHỈ trên payload bên dưới, nêu 1-3 nhận xét ngắn gọn "
            "bằng tiếng Việt có dấu. Chỉ dùng số xuất hiện trong allowed_numeric_facts hoặc table_preview; "
            "không tự đổi đơn vị, không ước lượng tỷ lệ, không dùng các cụm như gần một nửa/gấp đôi/tương đương, "
            "không nhắc JSON/context/planner/fallback/LLM. Mỗi nhận xét một câu, bắt đầu bằng '- '.\n\n"
            f"Câu hỏi: {message}\nPayload: {json.dumps(context, ensure_ascii=False, default=str)}"
        )
        validation_errors: list[str] = []
        try:
            llm = OllamaClient(self.settings).chat(
                [
                    {"role": "system", "content": "Bạn nêu nhận xét dữ liệu ngắn gọn, có căn cứ, bằng tiếng Việt có dấu."},
                    {"role": "user", "content": prompt},
                ]
            )
            text = (llm.text or "").strip()
            validation = validator.validate(text)
            if text and validation.passed:
                response.metadata["composer_validation_passed"] = True
                response.metadata["composer_validation_errors"] = []
                return f"Nhận xét:\n{text}" if not text.startswith("Nhận xét:") else text
            validation_errors = validation.errors
        except Exception as exc:
            validation_errors = [str(exc)]
        fallback_validation = validator.validate(fallback)
        response.metadata["composer_validation_passed"] = fallback_validation.passed
        response.metadata["composer_validation_errors"] = fallback_validation.errors
        response.metadata["composer_rejected_errors"] = validation_errors
        response.metadata["composer_fallback_used"] = True
        return fallback

    def _try_semantic_followup_response(
        self,
        conversation_id: str,
        message: str,
        state,
        debug: bool,
        started: float,
    ) -> ChatResponse | None:
        q = _ascii_text(message)
        if not _requests_commentary(q):
            return None
        # A commentary word ("nhan xet", "giai thich"...) is only a follow-up-only request
        # when the turn does NOT also contain a new analytical request. Otherwise commentary
        # is a presentation modifier layered on top of the analytics result (handled after the
        # query runs), so we must NOT hijack the intent here.
        if _has_new_analytics_request(q) and not _references_prior_result(q):
            return None
        if not state.last_result_summary and not state.last_plan and not _requires_dataset_level_semantic(q):
            return self._file_scope_response(
                conversation_id,
                "clarification",
                "Cần có kết quả trước đó",
                "Bạn muốn mình nhận xét dựa trên kết quả nào? Hãy hỏi một bảng, biểu đồ hoặc thống kê cụ thể trước.",
                "CLARIFICATION",
                debug,
                started,
                state,
                file_scope_validated=True,
            )
        if state.last_result_cache_id:
            record, cached_df = self.memory_service.load_result_reference(state.last_result_cache_id)
            if cached_df is not None and not cached_df.empty:
                display = format_dataframe_for_display(cached_df, None)
                table = _table_payload(display)
                temporary = ChatResponse(
                    message_id=str(uuid4()),
                    conversation_id=conversation_id,
                    response_type="table",
                    title="Kết quả trước đó",
                    summary="",
                    table=table,
                    metadata={},
                )
                commentary = deterministic_table_commentary(message, temporary)
                if commentary:
                    metadata = {
                        "execution_mode": "DETERMINISTIC",
                        "routing_reason": "semantic_followup_from_cached_result",
                        "llm_called": False,
                        "llm_call_count": 0,
                        "previous_visible_result_id": state.last_result_cache_id,
                        "previous_result_reference": record,
                        "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
                        "active_file_id": state.active_file_id,
                        "active_file_name": state.active_file_name,
                        "file_scope_validated": True,
                        "debug": {"cached_result_columns": list(cached_df.columns)} if debug else None,
                    }
                    return ChatResponse(
                        message_id=str(uuid4()),
                        conversation_id=conversation_id,
                        response_type="text",
                        title="Nhận xét kết quả",
                        summary=commentary,
                        metadata=_json_safe(metadata),
                    )
        context = {
            "source_file_name": state.active_file_name,
            "last_plan": state.last_plan,
            "last_result_summary": state.last_result_summary,
        }
        prompt = (
            "Bạn là trợ lý phân tích dữ liệu cho demo nội bộ. "
            "Dựa CHỈ trên context JSON bên dưới, trả lời ngắn gọn bằng tiếng Việt có dấu. "
            "Không bịa số mới, không nhắc đường dẫn local, không nói chung chung. "
            "Nếu context không đủ để kết luận, nói rõ giới hạn.\n\n"
            f"Câu hỏi người dùng: {message}\n"
            f"Context JSON: {json.dumps(context, ensure_ascii=False, default=str)}"
        )
        try:
            llm = OllamaClient(self.settings).chat(
                [
                    {"role": "system", "content": "Bạn trả lời phân tích dữ liệu ngắn gọn, có căn cứ, bằng tiếng Việt có dấu."},
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception as exc:
            return ChatResponse(
                message_id=str(uuid4()),
                conversation_id=conversation_id,
                response_type="error",
                title="Unable to generate analysis",
                summary="The language model could not generate this follow-up analysis." if not debug else str(exc),
                metadata={
                    "execution_mode": "SAFE_FAILURE",
                    "routing_reason": "semantic_followup_llm_error",
                    "llm_called": True,
                    "llm_call_count": 1,
                    "llm_request_started": True,
                    "llm_request_completed": False,
                    "fallback_used": True,
                    "fallback_reason": "semantic_followup_llm_error",
                    "llm_model": self.settings.ollama_model,
                    "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
                    "active_file_id": state.active_file_id,
                    "active_file_name": state.active_file_name,
                    "file_scope_validated": True,
                },
            )
        summary = llm.text.strip()
        metadata = {
            "execution_mode": "REAL_LLM",
            "routing_reason": "semantic_followup_from_last_result",
            "llm_called": True,
            "llm_call_count": 1,
            "llm_model": self.settings.ollama_model,
            "llm_latency_ms": round(llm.latency_ms, 1),
            "latency_ms": {"total": round((perf_counter() - started) * 1000, 1), "llm": round(llm.latency_ms, 1)},
            "active_file_id": state.active_file_id,
            "active_file_name": state.active_file_name,
            "file_scope_validated": True,
            "debug": {"semantic_followup_context": context} if debug else None,
        }
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="text",
            title="Nhận xét kết quả",
            summary=summary or "Mình chưa có đủ thông tin để đưa ra nhận xét chắc chắn.",
            metadata=metadata,
        )

    def _file_scope_response(
        self,
        conversation_id: str,
        response_type: str,
        title: str,
        summary: str,
        execution_mode: str,
        debug: bool,
        started: float,
        state,
        file_scope_validated: bool,
    ) -> ChatResponse:
        metadata = {
            "execution_mode": execution_mode,
            "router_confidence": 1.0,
            "routing_reason": "file_scope_preflight",
            "llm_called": False,
            "generated_sql": None,
            "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
            "debug": {"state_after": state.model_dump()} if debug else None,
        }
        self._attach_file_scope_to_metadata(metadata, state, file_scope_validated)
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,
            title=title,
            summary=summary,
            metadata=metadata,
        )

    def _attach_file_scope_metadata(self, response: ChatResponse, state, file_scope_validated: bool) -> None:
        self._attach_file_scope_to_metadata(response.metadata, state, file_scope_validated)

    def _attach_file_scope_to_metadata(self, metadata: dict[str, Any], state, file_scope_validated: bool) -> None:
        metadata["active_file_id"] = state.active_file_id
        metadata["active_file_name"] = state.active_file_name
        metadata["file_scope_validated"] = file_scope_validated

    def _prepare_response(self, response: ChatResponse, plan: QueryPlan | None = None) -> ChatResponse:
        if self.settings.show_internal_debug_metadata:
            response.metadata["internal_debug_metadata"] = _internal_debug_metadata(response, plan, self.settings.ollama_model)
        else:
            response.metadata.pop("internal_debug_metadata", None)
        return response

    def _save_assistant_response(
        self,
        state,
        response: ChatResponse,
        *,
        content: str | None = None,
        execution_mode: str | None = None,
        plan: QueryPlan | None = None,
        query_plan: dict | None = None,
        result_summary: dict | None = None,
        result_dataframe: pd.DataFrame | None = None,
    ) -> None:
        self._prepare_response(response, plan)
        self.memory_service.save_turn(
            state,
            role="assistant",
            content=content or response.primary_value or response.summary or response.title,
            execution_mode=execution_mode or response.metadata.get("execution_mode") or response.metadata.get("mode"),
            query_plan=query_plan,
            result_summary=result_summary,
            response_payload=response.model_dump(mode="json"),
            result_dataframe=result_dataframe,
        )

    def _plan_within_file_scope(self, plan: QueryPlan, catalog: dict) -> bool:
        if plan.intent in {"clarification", "refusal", "safe_failure"}:
            return True
        allowed = {table["table_name"] for table in catalog.get("tables", [])}
        return bool(plan.tables) and set(plan.tables).issubset(allowed)

    def describe_artifact(self, artifact_id: str) -> ArtifactPayload | None:
        path = self.resolve_artifact(artifact_id)
        if not path:
            return None
        return ArtifactPayload(id=path.name, filename=path.name, mime_type=_mime_type(path), size_bytes=path.stat().st_size)

    def resolve_artifact(self, artifact_id: str) -> Path | None:
        if not artifact_id or "/" in artifact_id or "\\" in artifact_id or ".." in artifact_id:
            return None
        path = (self.settings.reports_dir / artifact_id).resolve()
        reports_dir = self.settings.reports_dir.resolve()
        if path.parent != reports_dir or not path.exists() or not path.is_file():
            return None
        if path.suffix.lower() not in {".html", ".xlsx"}:
            return None
        return path

    def public_chat_response(self, response: ChatResponse) -> ChatResponse:
        if self.settings.show_internal_debug_metadata:
            return response
        return _customer_safe_response(response)

    def public_conversation_detail(self, detail: ConversationDetail) -> ConversationDetail:
        if self.settings.show_internal_debug_metadata:
            return detail
        messages = [
            message.model_copy(update={
                "execution_mode": None,
                "response": _customer_safe_response(message.response) if message.response else None,
            })
            for message in detail.messages
        ]
        return detail.model_copy(update={"messages": messages})

    def _try_metadata_response(
        self,
        conversation_id: str,
        message: str,
        intent: CustomerIntentResult,
        catalog: dict,
        debug: bool,
        started: float,
    ) -> ChatResponse | None:
        if intent.intent == "DATA_OVERVIEW":
            return self._data_overview_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "TABLE_OVERVIEW":
            return self._table_overview_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "ROW_COUNT":
            return self._row_count_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "PROVENANCE":
            return self._provenance_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "COLUMN_NULLS":
            return self._column_nulls_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "SCHEMA_INSPECTION":
            return self._schema_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "SAMPLE_ROWS":
            return self._sample_rows_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "DATA_RANGE":
            return self._data_range_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "DATA_QUALITY":
            return self._data_quality_response(conversation_id, intent, catalog, debug, started)
        if intent.intent == "REFUSAL":
            return self._simple_response(conversation_id, "refusal", "Không thể thực hiện", "Mình không thể thực hiện yêu cầu này vì nó nằm ngoài phạm vi phân tích dữ liệu an toàn.", intent, debug, started)
        if intent.intent == "CLARIFICATION":
            return self._simple_response(conversation_id, "clarification", "Cần làm rõ", "Bạn muốn xem tổng quan dữ liệu, schema, dữ liệu mẫu hay một thống kê cụ thể?", intent, debug, started)
        return None

    def _data_overview_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        rows = []
        lines = ["Hệ thống hiện có các bộ dữ liệu sau:"]
        for table in catalog.get("tables", []):
            name = _readable_table_name(table)
            columns = [col.get("normalized_name") for col in table.get("columns", []) if not str(col.get("normalized_name", "")).startswith("_")]
            time_range = _table_time_range(table)
            rows.append(
                {
                    "Bộ dữ liệu": name,
                    "Số bản ghi": format_vn_number(int(table.get("row_count") or 0), 0),
                    "Cột chính": ", ".join([str(col) for col in columns[:6]]),
                    "Khoảng thời gian": time_range or "",
                }
            )
            lines.append(f"- {name}: {format_vn_number(int(table.get('row_count') or 0), 0)} bản ghi")
        summary = "\n".join(lines) + "\nBạn có thể yêu cầu xem schema, dữ liệu mẫu, khoảng thời gian hoặc thống kê chi tiết của từng bộ dữ liệu."
        return self._metadata_response(
            conversation_id,
            "data_overview",
            "Tổng quan dữ liệu",
            summary,
            TablePayload(columns=["Bộ dữ liệu", "Số bản ghi", "Cột chính", "Khoảng thời gian"], rows=rows),
            intent,
            debug,
            started,
        )

    def _table_overview_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        table = self._resolve_table(intent, catalog) or (catalog.get("tables") or [None])[0]
        if not table:
            return self._simple_response(conversation_id, "clarification", "Cần làm rõ", "Bạn muốn xem bảng nào?", intent, debug, started)
        name = _readable_table_name(table)
        rows = [
            {"Thuộc tính": "Bộ dữ liệu", "Giá trị": name},
            {"Thuộc tính": "Số bản ghi", "Giá trị": format_vn_number(int(table.get("row_count") or 0), 0)},
            {"Thuộc tính": "Nguồn", "Giá trị": _safe_source_name(str(table.get("source", "")))},
            {"Thuộc tính": "Khoảng thời gian", "Giá trị": _table_time_range(table) or "Không có cột thời gian rõ ràng"},
            {"Thuộc tính": "Cột chính", "Giá trị": ", ".join(_business_column_names(table)[:10])},
        ]
        return self._metadata_response(
            conversation_id,
            "data_overview",
            f"{name} chứa gì?",
            f"{name} có {format_vn_number(int(table.get('row_count') or 0), 0)} bản ghi. Bạn có thể hỏi schema, dữ liệu mẫu hoặc thống kê chi tiết của bộ dữ liệu này.",
            TablePayload(columns=["Thuộc tính", "Giá trị"], rows=rows),
            intent,
            debug,
            started,
        )

    def _schema_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        tables = [self._resolve_table(intent, catalog)] if intent.table_hint else list(catalog.get("tables", []))
        tables = [table for table in tables if table]
        rows = []
        for table in tables:
            for col in table.get("columns", []):
                name = str(col.get("normalized_name") or col.get("name") or "")
                if name.startswith("_"):
                    continue
                rows.append(
                    {
                        "Bộ dữ liệu": _readable_table_name(table),
                        "Cột": humanize_column_name(name, catalog),
                        "Tên kỹ thuật": name,
                        "Kiểu": col.get("dtype") or col.get("type") or "",
                        "Vai trò": col.get("semantic_role") or col.get("role") or "",
                    }
                )
        return self._metadata_response(
            conversation_id,
            "schema",
            "Schema dữ liệu",
            f"Tìm thấy {format_vn_number(len(rows), 0)} cột có thể dùng để phân tích.",
            TablePayload(columns=["Bộ dữ liệu", "Cột", "Tên kỹ thuật", "Kiểu", "Vai trò"], rows=rows),
            intent,
            debug,
            started,
        )

    def _sample_rows_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        table = self._resolve_table(intent, catalog)
        if not table:
            return self._simple_response(conversation_id, "clarification", "Cần làm rõ", "Bạn muốn xem dữ liệu mẫu của bảng nào?", intent, debug, started)
        limit = intent.limit or 5
        path = _resolve_parquet_path(table.get("parquet_path") or table.get("cache_path"))
        if not path:
            return self._simple_response(conversation_id, "error", "Không có dữ liệu mẫu", "Không tìm thấy parquet cache cho bảng này.", intent, debug, started)
        df = pd.read_parquet(path).head(limit)
        display = format_dataframe_for_display(df, catalog)
        return self._metadata_response(
            conversation_id,
            "sample_table",
            f"{limit} dòng mẫu - {_readable_table_name(table)}",
            f"Hiển thị {min(limit, len(display))} bản ghi mẫu.",
            _table_payload(display),
            intent,
            debug,
            started,
        )

    def _data_range_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        rows = []
        for table in catalog.get("tables", []):
            time_range = _table_time_range(table)
            rows.append(
                {
                    "Bộ dữ liệu": _readable_table_name(table),
                    "Số bản ghi": format_vn_number(int(table.get("row_count") or 0), 0),
                    "Khoảng thời gian": time_range or "",
                    "Cột định danh": ", ".join([col for col in _business_column_names(table) if col in {"may", "cong", "ten_ton_that"}][:4]),
                }
            )
        return self._metadata_response(
            conversation_id,
            "data_overview",
            "Khoảng dữ liệu",
            "Đây là phạm vi dữ liệu hiện có theo từng bộ dữ liệu.",
            TablePayload(columns=["Bộ dữ liệu", "Số bản ghi", "Khoảng thời gian", "Cột định danh"], rows=rows),
            intent,
            debug,
            started,
        )

    def _data_quality_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        tables = [self._resolve_table(intent, catalog)] if intent.table_hint else list(catalog.get("tables", []))
        tables = [table for table in tables if table]
        rows = []
        for table in tables:
            path = _resolve_parquet_path(table.get("parquet_path") or table.get("cache_path"))
            if not path:
                continue
            df = pd.read_parquet(path)
            null_counts = df.isna().sum().sort_values(ascending=False)
            duplicate_count = int(df.duplicated().sum())
            rows.append(
                {
                    "Bộ dữ liệu": _readable_table_name(table),
                    "Số bản ghi": format_vn_number(len(df), 0),
                    "Dòng trùng": format_vn_number(duplicate_count, 0),
                    "Cột thiếu nhiều nhất": str(null_counts.index[0]) if len(null_counts) else "",
                    "Số giá trị thiếu": format_vn_number(int(null_counts.iloc[0]), 0) if len(null_counts) else "0",
                }
            )
        return self._metadata_response(
            conversation_id,
            "data_quality",
            "Chất lượng dữ liệu",
            "Tóm tắt nhanh null và dòng trùng theo từng bộ dữ liệu.",
            TablePayload(columns=["Bộ dữ liệu", "Số bản ghi", "Dòng trùng", "Cột thiếu nhiều nhất", "Số giá trị thiếu"], rows=rows),
            intent,
            debug,
            started,
        )

    def _row_count_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        table = self._resolve_table(intent, catalog) or (catalog.get("tables") or [None])[0]
        if not table:
            return self._simple_response(conversation_id, "clarification", "Cần làm rõ", "Bạn muốn đếm số bản ghi của bộ dữ liệu nào?", intent, debug, started)
        count = int(table.get("row_count") or 0)
        name = _readable_table_name(table)
        value = format_vn_number(count, 0)
        summary = (
            f"{name} hiện có {value} bản ghi. "
            "Con số được tính trên toàn bộ bảng của file đang chọn và không áp dụng bộ lọc bổ sung."
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="scalar",
            title="Số bản ghi",
            primary_value=value,
            summary=summary,
            sources=[SourcePayload(name=_safe_source_name(str(table.get("source", ""))), rows=count)],
            metadata=_metadata_for_customer_intent(intent, debug, started),
        )

    def _provenance_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        tables = list(catalog.get("tables", []))
        if not tables:
            return self._simple_response(conversation_id, "text", "Nguồn dữ liệu", "Hiện chưa có file dữ liệu nào được chọn cho cuộc trò chuyện này.", intent, debug, started)
        names: list[str] = []
        sources: list[SourcePayload] = []
        for table in tables:
            src = _safe_source_name(str(table.get("source", ""))) or _readable_table_name(table)
            src = _clean_source_filename(src)
            if src and src not in names:
                names.append(src)
                sources.append(SourcePayload(name=src, rows=int(table.get("row_count") or 0)))
        source_text = ", ".join(names)
        summary = (
            f"Kết quả trong cuộc trò chuyện này được lấy từ file nguồn: {source_text}. "
            "Mọi phân tích chỉ dựa trên dữ liệu của file này."
        )
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type="text",
            title="Nguồn dữ liệu",
            primary_value=source_text,
            summary=summary,
            sources=sources,
            metadata=_metadata_for_customer_intent(intent, debug, started),
        )

    def _column_nulls_response(self, conversation_id: str, intent: CustomerIntentResult, catalog: dict, debug: bool, started: float) -> ChatResponse:
        table = self._resolve_table(intent, catalog) or (catalog.get("tables") or [None])[0]
        if not table:
            return self._simple_response(conversation_id, "clarification", "Cần làm rõ", "Bạn muốn kiểm tra giá trị trống của bộ dữ liệu nào?", intent, debug, started)
        path = _resolve_parquet_path(table.get("parquet_path") or table.get("cache_path"))
        if not path:
            return self._simple_response(conversation_id, "error", "Không có dữ liệu", "Không tìm thấy dữ liệu cache cho bộ dữ liệu này.", intent, debug, started)
        df = pd.read_parquet(path)
        total = len(df)
        business = set(_business_column_names(table))
        keep = [col for col in df.columns if str(col) in business] if business else [col for col in df.columns if not str(col).startswith("_")]
        null_counts = df[keep].isna().sum().sort_values(ascending=False) if keep else df.isna().sum().sort_values(ascending=False)
        rows = []
        for col, cnt in null_counts.items():
            name = str(col)
            if name.startswith("_"):
                continue
            cnt = int(cnt)
            pct = (cnt / total * 100) if total else 0.0
            rows.append(
                {
                    "Cột": humanize_column_name(name, catalog),
                    "Số giá trị trống": format_vn_number(cnt, 0),
                    "Tỷ lệ trống": f"{format_vn_number(pct, 1)}%",
                }
            )
        rows = rows[:10]
        if len(null_counts) and int(null_counts.iloc[0]) > 0:
            top_name = humanize_column_name(str(null_counts.index[0]), catalog)
            top_cnt = int(null_counts.iloc[0])
            summary = (
                f"Cột có nhiều giá trị trống nhất là “{top_name}” với {format_vn_number(top_cnt, 0)} giá trị trống "
                f"({format_vn_number(top_cnt / total * 100, 1)}% trên {format_vn_number(total, 0)} bản ghi). "
                "Bảng dưới liệt kê các cột theo số giá trị trống giảm dần."
            )
        else:
            summary = f"Không phát hiện giá trị trống nào trong {format_vn_number(total, 0)} bản ghi của bộ dữ liệu này."
        return self._metadata_response(
            conversation_id,
            "data_quality",
            "Cột có nhiều giá trị trống nhất",
            summary,
            TablePayload(columns=["Cột", "Số giá trị trống", "Tỷ lệ trống"], rows=rows),
            intent,
            debug,
            started,
        )

    def _metadata_response(
        self,
        conversation_id: str,
        response_type: str,
        title: str,
        summary: str,
        table: TablePayload | None,
        intent: CustomerIntentResult,
        debug: bool,
        started: float,
    ) -> ChatResponse:
        metadata = _metadata_for_customer_intent(intent, debug, started)
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,
            title=title,
            summary=summary,
            table=table,
            metadata=metadata,
        )

    def _simple_response(
        self,
        conversation_id: str,
        response_type: str,
        title: str,
        summary: str,
        intent: CustomerIntentResult,
        debug: bool,
        started: float,
    ) -> ChatResponse:
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,
            title=title,
            summary=summary,
            metadata=_metadata_for_customer_intent(intent, debug, started),
        )

    def _resolve_table(self, intent: CustomerIntentResult, catalog: dict) -> dict | None:
        tables = catalog.get("tables", [])
        if len(tables) == 1:
            return tables[0]
        if not intent.table_hint:
            return None
        return next((table for table in tables if intent.table_hint in str(table.get("table_name", "")).lower() or intent.table_hint in str(table.get("source", "")).lower()), None)

    def _sources_for_plan(self, plan: QueryPlan, catalog: dict) -> list[dict]:
        return [
            {"table": table["table_name"], "source": table["source"], "rows": table["row_count"]}
            for table in catalog.get("tables", [])
            if table["table_name"] in plan.tables
        ]

    def _response_from_presented(
        self,
        conversation_id: str,
        presented: PresentedResponse,
        plan: QueryPlan,
        raw_dataframe: pd.DataFrame | None,
        catalog: dict,
        metadata: dict[str, Any],
        html_path: Path | None,
        xlsx_path: Path | None,
    ) -> ChatResponse:
        response_type = _response_type(presented, plan)
        table = _table_payload(presented.result_dataframe) if presented.result_dataframe is not None else None
        chart = _chart_payload(raw_dataframe, plan, catalog, metadata) if raw_dataframe is not None and plan.output in {"bar", "horizontal_bar", "line", "pie"} else None
        dashboard = None
        if response_type == "dashboard" and raw_dataframe is not None:
            dashboard = DashboardPayload(cards=kpi_cards(raw_dataframe), table=table, chart=chart)
        downloads = [_download_payload(path) for path in [html_path, xlsx_path] if path and path.exists()]
        summary = _rich_result_summary(presented, plan, raw_dataframe, metadata, response_type)
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,
            title=presented.title,
            summary=summary,
            primary_value=presented.primary_value,
            secondary_value=presented.secondary_value,
            table=table if response_type != "scalar" else None,
            chart=chart,
            dashboard=dashboard,
            sources=_source_payloads(self._sources_for_plan(plan, catalog)),
            filters=_filter_payloads(plan, catalog),
            downloads=downloads,
            metadata=_json_safe(metadata),
        )

    def _debug_payload(self, enabled: bool, plan: QueryPlan, sql: str | None, state) -> dict[str, Any] | None:
        if not enabled:
            return None
        return {"query_plan": plan.model_dump(), "sql": sql, "state_after": state.model_dump()}

    def _set_title_from_first_message(self, conversation_id: str, message: str) -> None:
        record = self.memory_service.get_conversation(conversation_id)
        if not record:
            return
        title = str(record.get("title") or "")
        if title.strip().lower().startswith("hoi thoai") or title.strip().lower().startswith("cuộc trò chuyện"):
            self.memory_service.update_conversation(conversation_id, title=message[:64])


def _response_type(presented: PresentedResponse, plan: QueryPlan) -> str:
    if plan.intent == "refusal":
        return "refusal"
    if plan.intent == "safe_failure":
        return "error"
    if plan.intent == "clarification":
        return "clarification"
    if presented.response_type == "report":
        return "report"
    if presented.response_type in {"scalar", "table", "chart", "dashboard"}:
        return presented.response_type
    return "text"


def _table_payload(df: pd.DataFrame) -> TablePayload:
    safe_df = df.copy()
    safe_df.columns = _unique_columns([str(column) for column in safe_df.columns])
    rows = [_json_safe(row) for row in safe_df.to_dict(orient="records")]
    return TablePayload(columns=[str(column) for column in safe_df.columns], rows=rows)


def _chart_payload(df: pd.DataFrame, plan: QueryPlan, catalog: dict, metadata: dict[str, Any] | None = None) -> ChartPayload | None:
    if df.empty or len(df.columns) < 2 or plan.output not in {"bar", "horizontal_bar", "line", "pie"}:
        return None
    x = plan.dimensions[0] if plan.dimensions and plan.dimensions[0] in df.columns else df.columns[0]
    y_candidates = [metric.name or f"{metric.aggregation}_{metric.column}" for metric in plan.metrics]
    y = next((column for column in y_candidates if column in df.columns), df.columns[-1])
    if y == x:
        y = next((column for column in df.columns if column != x), y)
    x_label = humanize_column_name(str(x), catalog)
    y_axis_unit = None
    tooltip_unit = None
    chart_df = df[[x, y]].head(100).copy()
    if _is_duration_metric(str(y), plan):
        unit, divisor = _duration_display_unit(chart_df[y])
        y_axis_unit = unit
        tooltip_unit = unit
        y_label = f"{humanize_column_name(str(y), catalog)} ({unit})"
        chart_df[y] = pd.to_numeric(chart_df[y], errors="coerce").fillna(0) / divisor
        chart_df[y] = chart_df[y].round(2)
    else:
        y_label = humanize_column_name(str(y), catalog)
    data = chart_df.rename(columns={x: x_label, y: y_label}).to_dict(orient="records")
    lineage = (metadata or {}).get("lineage") if isinstance(metadata, dict) else None
    source_result_id = str((lineage or {}).get("query_result_id") or (metadata or {}).get("query_result_id") or "")
    source_turn_id = str((lineage or {}).get("turn_id") or "")
    chart_contract = ChartContract(
        chart_type=plan.output,
        dimension=_normalized_contract_dimension(str(x)),
        metric=_normalized_contract_metric(str(y)),
        aggregation=plan.metrics[0].aggregation if plan.metrics else "count",
        x_axis_unit=None,
        y_axis_unit=y_axis_unit,
        tooltip_unit=tooltip_unit,
        source_result_id=source_result_id,
        source_turn_id=source_turn_id,
        expected_category_count=int(min(len(chart_df), 100)),
        time_grain=plan.time_granularity,
    )
    if isinstance(metadata, dict):
        metadata["chart_contract"] = chart_contract.model_dump()
    return ChartPayload(
        type=plan.output,
        title="Kết quả phân tích",
        x_key=x_label,
        y_keys=[y_label],
        data=_json_safe(data),
        y_axis_unit=y_axis_unit,
        tooltip_unit=tooltip_unit,
        source_result_id=source_result_id or None,
        source_turn_id=source_turn_id or None,
        metric=chart_contract.metric,
        dimension=chart_contract.dimension,
    )


def _is_duration_metric(column: str, plan: QueryPlan) -> bool:
    if "duration_seconds" in column or column.endswith("_seconds"):
        return True
    return any((metric.column or "").endswith("_seconds") or "duration" in (metric.column or "") for metric in plan.metrics)


def _duration_display_unit(values: pd.Series) -> tuple[str, float]:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0).abs()
    max_value = float(numeric.max()) if not numeric.empty else 0.0
    if max_value >= 7200:
        return "giờ", 3600.0
    if max_value >= 60:
        return "phút", 60.0
    return "giây", 1.0


def _normalized_contract_dimension(column: str) -> str:
    mapping = {
        "may": "machine",
        "machine_name": "machine",
        "nhom_ton_that": "loss_group",
        "loss_group": "loss_group",
        "ten_ton_that": "loss_name",
        "loss_name": "loss_name",
        "thoi_gian_bat_dau": "date",
        "start_time": "date",
        "report_date": "date",
    }
    return mapping.get(column, column)


def _normalized_contract_metric(column: str) -> str:
    mapping = {
        "total_duration_seconds": "total_downtime",
        "avg_duration_seconds": "average_duration",
        "row_count": "count",
        "percentage": "percentage",
    }
    return mapping.get(column, column)


def _role_column(table: dict, role: str) -> str | None:
    for column in table.get("columns", []):
        if column.get("semantic_role") == role:
            return str(column.get("normalized_name") or "")
    return None


def _report_summary(
    report_kind: str,
    record_count: int,
    total_hours: float,
    date_range: dict[str, str] | None,
    top_machines: pd.DataFrame,
    top_causes: pd.DataFrame,
) -> str:
    range_text = f"{date_range['from']} đến {date_range['to']}" if date_range else "không xác định"
    lines = [
        f"Báo cáo đã tổng hợp {record_count} dòng dữ liệu trong giai đoạn {range_text}.",
        f"Tổng downtime là {format_vn_number(total_hours, 2)} giờ.",
    ]
    if not top_machines.empty:
        first = top_machines.iloc[0]
        lines.append(f"Máy đứng đầu theo downtime là {first.iloc[0]} với {format_vn_number(float(first['total_duration_seconds']) / 3600, 2)} giờ.")
    if report_kind == "downtime" and not top_causes.empty:
        first = top_causes.iloc[0]
        lines.append(f"Nguyên nhân tổn thất lớn nhất là {first.iloc[0]} với {format_vn_number(float(first['total_duration_seconds']) / 3600, 2)} giờ.")
    lines.append("Report includes overview, KPI, ranked tables, time trend, source and limitation sections.")
    return "\n".join(lines)


def _export_orchestrated_report(
    *,
    message: str,
    report_kind: str,
    summary: str,
    sections: dict[str, dict[str, Any]],
    top_machines: pd.DataFrame,
    top_causes: pd.DataFrame,
    trend: pd.DataFrame,
    reports_dir: Path,
    artifact_id: str,
    catalog: dict,
) -> tuple[Path, Path]:
    from datetime import datetime, timezone

    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"report_{artifact_id}"
    html_path = reports_dir / f"{stem}.html"
    xlsx_path = reports_dir / f"{stem}.xlsx"
    generated_at = datetime.now(timezone.utc).isoformat()
    chart_svg = _trend_svg_snapshot(trend)
    html_parts = [
        "<html><head><meta charset=\"utf-8\"><title>Gopak report</title></head><body>",
        f"<h1>{'Downtime report' if report_kind == 'downtime' else 'Overview report'}</h1>",
        f"<p><strong>Generated:</strong> {generated_at}</p>",
        f"<p><strong>Question:</strong> {message}</p>",
        "".join(f"<p>{line}</p>" for line in summary.splitlines()),
        "<h2>Source and filters</h2>",
        "<p>Source: selected uploaded workbook. Filters: none unless stated in the question.</p>",
        "<h2>Section status</h2>",
        pd.DataFrame([{"section": key, **value} for key, value in sections.items()]).to_html(index=False),
        "<h2>Chart</h2>",
        chart_svg or "<p>No chart data available.</p>",
    ]
    for title, frame in [("Top machines", top_machines), ("Top causes", top_causes), ("Time trend", trend)]:
        html_parts.append(f"<h2>{title}</h2>")
        html_parts.append(format_dataframe_for_display(frame, catalog).to_html(index=False) if not frame.empty else "<p>No data.</p>")
    html_parts.append("</body></html>")
    html_path.write_text("\n".join(html_parts), encoding="utf-8")
    with pd.ExcelWriter(xlsx_path) as writer:
        pd.DataFrame([{"section": key, **value} for key, value in sections.items()]).to_excel(writer, sheet_name="section_status", index=False)
        if not top_machines.empty:
            _report_numeric_frame(top_machines).to_excel(writer, sheet_name="top_machines", index=False)
        if not top_causes.empty:
            _report_numeric_frame(top_causes).to_excel(writer, sheet_name="top_causes", index=False)
        if not trend.empty:
            _report_numeric_frame(trend).to_excel(writer, sheet_name="time_trend", index=False)
    return html_path, xlsx_path


def _report_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    for column in list(frame.columns):
        if str(column).endswith("_duration_seconds"):
            frame[str(column).replace("_duration_seconds", "_downtime_hours")] = pd.to_numeric(frame[column], errors="coerce") / 3600
            frame = frame.drop(columns=[column])
        elif str(column).endswith("_seconds"):
            frame[str(column).replace("_seconds", "_hours")] = pd.to_numeric(frame[column], errors="coerce") / 3600
            frame = frame.drop(columns=[column])
    return frame


def _trend_svg_snapshot(trend: pd.DataFrame) -> str:
    if trend.empty or "total_duration_seconds" not in trend.columns:
        return ""
    values = (pd.to_numeric(trend["total_duration_seconds"], errors="coerce").fillna(0) / 3600).head(60).tolist()
    if not values:
        return ""
    width, height, pad = 720, 220, 24
    max_value = max(values) or 1
    step = (width - pad * 2) / max(1, len(values) - 1)
    points = []
    for idx, value in enumerate(values):
        x = pad + idx * step
        y = height - pad - (float(value) / max_value) * (height - pad * 2)
        points.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg role="img" aria-label="Daily downtime trend chart" width="{width}" height="{height}" '
        'viewBox="0 0 720 220" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="720" height="220" fill="#ffffff"/>'
        '<text x="24" y="20" font-size="14">Daily downtime trend (hours)</text>'
        f'<polyline fill="none" stroke="#7c8fd6" stroke-width="2" points="{" ".join(points)}"/>'
        "</svg>"
    )


def _source_payloads(sources: list[dict]) -> list[SourcePayload]:
    return [
        SourcePayload(name=_safe_source_name(str(item.get("source", ""))), rows=int(item.get("rows") or 0))
        for item in sources
    ]


def _filter_payloads(plan: QueryPlan, catalog: dict) -> list[FilterPayload]:
    return [
        FilterPayload(label=humanize_column_name(item.column, catalog), operator=item.operator, value=_json_safe(item.value))
        for item in plan.filters
    ]


def _download_payload(path: Path) -> DownloadPayload:
    label = "Tải HTML" if path.suffix.lower() == ".html" else "Tải Excel"
    return DownloadPayload(id=path.name, label=label, filename=path.name, mime_type=_mime_type(path))


def _conversation_payload(item: dict[str, Any]) -> ConversationPayload:
    return ConversationPayload(
        id=str(item.get("id", "")),
        title=_display_title(str(item.get("title") or "Cuộc trò chuyện")),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
        status=str(item.get("status") or "active"),
    )


def _display_title(title: str) -> str:
    if title.strip().lower().startswith("hoi thoai"):
        return "Cuộc trò chuyện"
    return title


def _readable_table_name(table: dict) -> str:
    source = str(table.get("source", ""))
    if "Machine_Downtime" in source:
        return "Downtime máy"
    if "Loss_Assignment" in source:
        return "Phân loại tổn thất"
    if "EntryTransaction" in source:
        return "Ra vào cổng"
    return str(table.get("table_name", "Bảng dữ liệu"))


def _safe_source_name(source: str) -> str:
    if " / " in source:
        file_part, sheet = source.split(" / ", 1)
        return f"{Path(file_part).name} · {sheet}"
    return Path(source).name or source


def _clean_source_filename(source: str) -> str:
    """Return just the workbook filename, dropping any ' · sheet/report' suffix."""
    text = str(source or "").strip()
    lowered = text.lower()
    for ext in (".xlsx", ".xls"):
        idx = lowered.rfind(ext)
        if idx != -1:
            return text[: idx + len(ext)]
    return text.split(" · ")[0].strip()


def _mime_type(path: Path) -> str:
    if path.suffix.lower() == ".html":
        return "text/html"
    if path.suffix.lower() == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def _unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        count = seen.get(column, 0)
        seen[column] = count + 1
        result.append(column if count == 0 else f"{column} ({count + 1})")
    return result


def _stored_chat_response(value: Any) -> ChatResponse | None:
    if not value:
        return None
    try:
        payload = json.loads(str(value)) if isinstance(value, str) else value
        return ChatResponse.model_validate(payload)
    except Exception:
        return None


def _customer_safe_response(response: ChatResponse) -> ChatResponse:
    safe_metadata = {}
    for key in ["active_file_id", "active_file_name", "file_scope_validated"]:
        if key in response.metadata:
            safe_metadata[key] = response.metadata[key]
    return response.model_copy(deep=True, update={"metadata": safe_metadata})


def _rich_result_summary(
    presented: PresentedResponse,
    plan: QueryPlan,
    raw_dataframe: pd.DataFrame | None,
    metadata: dict[str, Any],
    response_type: str,
) -> str:
    base = (presented.summary or presented.primary_value or "").strip()
    source = str(metadata.get("active_file_name") or "")
    scope = "Kết quả được tính trên file đang chọn"
    if source:
        scope = f"Kết quả được tính trên file {source}"
    if plan.filters:
        scope += " với các bộ lọc đang hiển thị bên dưới."
    else:
        scope += " và không áp dụng bộ lọc bổ sung."

    if response_type == "scalar":
        direct = base or (presented.primary_value or "")
        return " ".join(part for part in [direct, scope] if part).strip()

    if raw_dataframe is not None and not raw_dataframe.empty and (plan.ranking or plan.limit or plan.sort):
        metric_note = "Bảng được sắp xếp giảm dần theo chỉ tiêu chính để bạn dễ so sánh các nhóm đứng đầu."
        return " ".join(part for part in [base, metric_note, scope] if part).strip()

    if response_type == "chart":
        return " ".join(
            part
            for part in [
                base,
                "Biểu đồ dùng cùng dữ liệu và đơn vị với bảng kết quả, nên có thể dùng để so sánh trực quan các nhóm nổi bật.",
                scope,
            ]
            if part
        ).strip()

    if response_type in {"table", "report"}:
        return " ".join(part for part in [base, "Bảng bên dưới giữ nguyên thứ tự và giá trị đã tính từ truy vấn.", scope] if part).strip()

    return base


def _internal_debug_metadata(response: ChatResponse, plan: QueryPlan | None, model: str) -> dict[str, Any]:
    metadata = response.metadata or {}
    latency = metadata.get("latency_ms") if isinstance(metadata.get("latency_ms"), dict) else {}
    llm_latency = metadata.get("llm_latency_ms")
    if llm_latency is None and isinstance(latency, dict):
        llm_latency = latency.get("llm")
    source_file_ids = []
    active_file_id = metadata.get("active_file_id")
    if active_file_id:
        source_file_ids.append(str(active_file_id))
    filters = []
    if response.filters:
        filters = [item.model_dump(mode="json") for item in response.filters]
    elif plan is not None:
        filters = [flt.model_dump(mode="json") for flt in plan.filters]
    query_plan_summary = None
    if plan is not None:
        query_plan_summary = {
            "intent": plan.intent,
            "output": plan.output,
            "tables": list(plan.tables),
            "metrics": [metric.model_dump(mode="json") for metric in plan.metrics],
            "dimensions": list(plan.dimensions),
            "limit": plan.limit,
        }
    return {
        "execution_mode": metadata.get("execution_mode") or metadata.get("mode"),
        "llm_called": bool(metadata.get("llm_called")),
        "llm_model": metadata.get("llm_model") or (model if metadata.get("llm_called") else None),
        "llm_latency_ms": llm_latency,
        "route_reason": metadata.get("routing_reason") or metadata.get("route_reason") or "",
        "response_type": response.response_type,
        "active_file_id": active_file_id,
        "active_file_name": metadata.get("active_file_name"),
        "source_file_ids": source_file_ids,
        "filters_summary": filters,
        "query_plan_summary": query_plan_summary,
    }


def _metadata_for_customer_intent(intent: CustomerIntentResult, debug: bool, started: float) -> dict[str, Any]:
    return {
        "execution_mode": intent.intent,
        "router_confidence": intent.confidence,
        "routing_reason": intent.reason,
        "llm_called": False,
        "generated_sql": None,
        "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
        "debug": {"customer_intent": intent.__dict__} if debug else None,
    }


def _business_column_names(table: dict) -> list[str]:
    return [
        str(col.get("normalized_name") or col.get("name") or "")
        for col in table.get("columns", [])
        if not str(col.get("normalized_name") or col.get("name") or "").startswith("_")
    ]


def _table_time_range(table: dict) -> str | None:
    for col in table.get("columns", []):
        role = col.get("semantic_role") or col.get("role")
        name = str(col.get("normalized_name") or col.get("name") or "")
        if role == "start_time" or "thoi_gian" in name or "time" in name:
            min_value = col.get("min")
            max_value = col.get("max")
            if min_value and max_value:
                return f"{min_value} đến {max_value}"
    return None


def _resolve_parquet_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.is_absolute():
        path = get_settings().root / path
    return path if path.exists() else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return [_json_safe(row) for row in value.to_dict(orient="records")]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (list, tuple, dict)) else False:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _conversation_payload(item: dict[str, Any], state: Any | None = None) -> ConversationPayload:
    source_file_id = str(item.get("source_file_id") or getattr(state, "active_file_id", "") or "") or None
    source_file_name = str(item.get("source_file_name") or getattr(state, "active_file_name", "") or "") or None
    return ConversationPayload(
        id=str(item.get("id", "")),
        title=_display_title(str(item.get("title") or "Cuoc tro chuyen")),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
        status=str(item.get("status") or "active"),
        source_file_id=source_file_id,
        source_file_name=source_file_name,
        source_file_sha256=str(item.get("source_file_sha256") or "") or None,
        source_catalog_version=str(item.get("source_catalog_version") or "") or None,
        source_available=bool(find_uploaded_file(source_file_id)) if source_file_id else True,
        active_file_id=source_file_id,
        active_file_name=source_file_name,
    )


def _table_source_filename(table: dict) -> str:
    source = str(table.get("source") or "")
    file_part = source.split(" / ", 1)[0]
    return Path(file_part).name


def _table_file_id(table: dict) -> str:
    profile = table.get("profile") if isinstance(table.get("profile"), dict) else {}
    return str(table.get("file_id") or table.get("source_file_id") or profile.get("source_file_id") or "")


def _starts_slot_clarification(message: str) -> bool:
    import re

    q = _ascii_text(message).strip(" ?.!;:")
    q = re.sub(r"\s*#\d+\s*$", "", q).strip()
    if q in {"top", "top may", "top nguyen nhan"}:
        return True
    chart_requested = any(term in q for term in ["bieu do", "chart", "ve cot", "ve line", "ve chart", "ve bieu do"])
    overview_requested = any(term in q for term in ["tong quan", "overview"])
    has_grouping = any(term in q for term in ["theo", "may", "nguyen nhan", "nhom", "cong"])
    has_metric = any(term in q for term in ["downtime", "thoi gian", "thoi luong", "so lan", "dem", "count"])
    return chart_requested and overview_requested and not (has_grouping or has_metric)


def _ascii_text(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


_COMMENTARY_TERMS = [
    "nhan xet", "danh gia", "giai thich", "noi len dieu gi", "y nghia", "insight",
    "binh luan", "diem dang chu y", "dang chu y", "phan tich giup", "quan trong nhat",
]
_PRIOR_RESULT_REFS = [
    "vua roi", "tren day", "ket qua tren", "ket qua nay", "ket qua do", "ket qua vua roi",
    "bang nay", "bang tren", "bang vua roi", "bang do", "bieu do nay", "o tren", "phia tren", "vua xong",
]
_ANALYTICS_RANKING_WORDS = ["top", "bottom", "cao nhat", "thap nhat", "nhieu nhat", "it nhat", "dung dau", "xep hang", "pho bien", "quan trong"]
_ANALYTICS_DIM_NOUNS = ["may", "machine", "nhom", "ton that", "nguyen nhan", "cong", "loai", "thang", "ngay"]
_ANALYTICS_METRIC_WORDS = ["downtime", "thoi gian", "thoi luong", "so lan", "so luot", "ghi nhan", "dem", "tong", "trung binh", "gia tri", "count", "luong xe", "ra vao"]


def _requests_commentary(q: str) -> bool:
    """True if the (ascii-normalized) message asks for narrative commentary/explanation."""
    return any(term in q for term in _COMMENTARY_TERMS)


def _references_prior_result(q: str) -> bool:
    return any(term in q for term in _PRIOR_RESULT_REFS)


def _requires_dataset_level_semantic(q: str) -> bool:
    return any(
        term in q
        for term in [
            "toan bo du lieu",
            "dua tren toan bo",
            "diem dang chu y",
            "dang quan tam",
            "bat thuong",
            "so sanh",
            "gioi han",
            "ket luan",
            "insight",
            "quan trong",
            "luong xe",
            "ra vao cong",
            "nhom ton that",
        ]
    )


def _is_open_ended_dataset_analysis(q: str) -> bool:
    has_scope = any(term in q for term in ["toan bo du lieu", "dua tren toan bo", "file nay", "du lieu nay", "data nay", "file", "data", "du lieu"])
    has_open_ended = any(term in q for term in ["diem dang chu y", "dang chu y", "co gi dang chu y", "dang quan tam", "bat thuong", "giai thich", "so sanh", "gioi han", "ket luan", "insight", "phan tich", "tom tat", "tinh hinh chung", "cho quan ly", "van de gi"])
    explicit_table_request = bool(_extract_top_n(q)) or any(term in q for term in ["theo may", "theo nhom", "theo nguyen nhan", "bang", "bieu do"])
    return has_scope and has_open_ended and not explicit_table_request


def _extract_top_n(q: str) -> int | None:
    import re

    match = re.search(r"top\s*(\d{1,2})", q)
    return int(match.group(1)) if match else None


def _has_new_analytics_request(q: str) -> bool:
    """True if the (ascii-normalized) message carries a self-contained analytical request
    (dimension + ranking/metric), independent of any trailing commentary/output modifier."""
    import re

    has_rank = any(word in q for word in _ANALYTICS_RANKING_WORDS)
    has_dim = any(noun in q for noun in _ANALYTICS_DIM_NOUNS)
    has_metric = any(word in q for word in _ANALYTICS_METRIC_WORDS)
    if re.search(r"top\s*\d", q):
        return True
    if has_rank and has_dim:
        return True
    if "theo" in q and has_dim:
        return True
    if has_metric and has_dim:
        return True
    return False

