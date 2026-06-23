from __future__ import annotations

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
from src.catalog.profiler import load_catalog
from src.conversation.clarification import ClarificationResolver, build_plan_from_resolved_message, restore_topic_plan
from src.config import Settings, get_settings
from src.conversation.memory_service import ConversationMemoryService
from src.application.customer_intents import CustomerIntentResult, detect_customer_intent
from src.application.row_level import try_row_level_response
from src.files.lifecycle import FileLifecycleService
from src.files.upload_store import find_uploaded_file, list_uploaded_files
from src.llm.ollama_client import OllamaClient
from src.llm.planner import QueryPlanner
from src.query.executor import SafeQueryExecutor
from src.query.schemas import QueryPlan
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
            catalog = self.get_catalog(force=True)
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

    def create_conversation(self, title: str | None = None) -> ConversationPayload:
        state = self.memory_service.create_conversation(title=title)
        record = self.memory_service.get_conversation(state.conversation_id)
        return _conversation_payload(
            record or {"id": state.conversation_id, "title": title or "Cuoc tro chuyen", "created_at": "", "updated_at": "", "status": "active"},
            state,
        )

    def list_conversations(self) -> list[ConversationPayload]:
        payloads = []
        for item in self.memory_service.list_conversations():
            state = self.memory_service.load_conversation(str(item.get("id", "")))
            payloads.append(_conversation_payload(item, state))
        return payloads

    def get_conversation(self, conversation_id: str, limit: int = 200) -> ConversationDetail | None:
        record = self.memory_service.get_conversation(conversation_id)
        if not record or record.get("status") == "deleted":
            return None
        state = self.memory_service.load_conversation(conversation_id)
        if state.active_file_id and not find_uploaded_file(state.active_file_id):
            state.active_file_id = None
            state.active_file_name = None
            self.memory_service.save_state(state)
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
        if not self.memory_service.get_conversation(conversation_id):
            return None
        record = find_uploaded_file(file_id)
        if not record:
            raise ValueError("File not found")
        if record.get("status") != "ready" or not record.get("queryable"):
            raise ValueError("File is not ready")
        readiness = FileLifecycleService(self.settings).validate_readiness(file_id, catalog=self.get_catalog(force=True))
        if not readiness.get("ok"):
            raise ValueError(str(readiness.get("message") or "File is not queryable"))
        state = self.memory_service.load_conversation(conversation_id)
        state.save_file_context()
        state.active_file_id = str(record.get("id") or "")
        state.active_file_name = str(record.get("filename") or "")
        state.restore_file_context(state.active_file_id)
        self.memory_service.save_state(state)
        return ActiveFilePayload(
            conversation_id=conversation_id,
            active_file_id=state.active_file_id,
            active_file_name=state.active_file_name,
            status="ready",
        )

    def process_message(self, conversation_id: str, message: str, debug: bool = False) -> ChatResponse:
        started = perf_counter()
        message = message.strip()
        catalog = self.get_catalog()
        state = self.memory_service.load_conversation(conversation_id)
        if not self.memory_service.get_conversation(conversation_id):
            state = self.memory_service.create_conversation()
            conversation_id = state.conversation_id

        self._set_title_from_first_message(conversation_id, message)
        self.memory_service.save_turn(state, role="user", content=message)

        customer_intent = detect_customer_intent(message)
        metadata_response = self._try_metadata_response(conversation_id, message, customer_intent, catalog, debug, started)
        if metadata_response is not None:
            self.memory_service.save_turn(
                state,
                role="assistant",
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

    def process_message(self, conversation_id: str, message: str, debug: bool = False) -> ChatResponse:
        started = perf_counter()
        message = message.strip()
        state = self.memory_service.load_conversation(conversation_id)
        if not self.memory_service.get_conversation(conversation_id):
            state = self.memory_service.create_conversation()
            conversation_id = state.conversation_id

        self._set_title_from_first_message(conversation_id, message)
        self.memory_service.save_turn(state, role="user", content=message)

        preflight = self._preflight_file_scope(conversation_id, state, message, debug, started)
        if preflight is not None:
            self.memory_service.save_turn(
                state,
                role="assistant",
                content=preflight.summary or preflight.title,
                execution_mode=preflight.metadata.get("execution_mode"),
            )
            return preflight

        catalog = self.get_catalog_for_file(state.active_file_id or "")
        if not catalog.get("tables"):
            response = self._file_scope_response(
                conversation_id,
                "error",
                "Khong the dung file nay",
                "File dang chon chua co bang du lieu trong catalog. Vui long nap lai du lieu hoac chon file khac.",
                "SAFE_FAILURE",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
            self.memory_service.save_turn(state, role="assistant", content=response.summary, execution_mode="SAFE_FAILURE")
            return response

        clarification = ClarificationResolver(catalog).resolve_pending(
            conversation_id,
            message,
            state,
            debug=debug,
            started=started,
        )
        if clarification.response is not None:
            self.memory_service.save_turn(
                state,
                role="assistant",
                content=clarification.response.summary or clarification.response.title,
                execution_mode=clarification.response.metadata.get("execution_mode"),
            )
            return clarification.response
        if clarification.resolved_message:
            message = clarification.resolved_message
        forced_plan = build_plan_from_resolved_message(catalog, state, message) if clarification.resolved_message else None
        if forced_plan is None:
            forced_plan = restore_topic_plan(catalog, state, message)
        if forced_plan is None and state.pending_clarification is None and _starts_slot_clarification(message):
            started_clarification = ClarificationResolver(catalog).maybe_start(
                conversation_id,
                message,
                state,
                QueryPlan(intent="clarification", output="text", clarification_question="Cần làm rõ yêu cầu."),
                debug=debug,
                started=started,
            )
            if started_clarification is not None:
                self.memory_service.save_turn(
                    state,
                    role="assistant",
                    content=started_clarification.summary or started_clarification.title,
                    execution_mode=started_clarification.metadata.get("execution_mode"),
                )
                return started_clarification

        row_response = try_row_level_response(conversation_id, message, catalog, state, debug, started)
        if row_response is not None:
            self.memory_service.save_turn(
                state,
                role="assistant",
                content=row_response.summary or row_response.title,
                execution_mode=row_response.metadata.get("execution_mode"),
                query_plan=None,
                result_summary=None,
            )
            return row_response

        customer_intent = detect_customer_intent(message)
        metadata_response = self._try_metadata_response(conversation_id, message, customer_intent, catalog, debug, started)
        if metadata_response is not None:
            self._attach_file_scope_metadata(metadata_response, state, True)
            self.memory_service.save_turn(
                state,
                role="assistant",
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
                planned = planner.plan(message, state)
                plan = planned.plan
                metadata = dict(planned.metadata or {})
            metadata["persistence_degraded"] = self.memory_service.persistence_degraded
            self._attach_file_scope_to_metadata(metadata, state, True)

            if not self._plan_within_file_scope(plan, catalog):
                metadata["execution_mode"] = "SAFE_FAILURE"
                metadata["file_scope_validated"] = False
                allowed = {table["table_name"] for table in catalog.get("tables", [])}
                metadata["file_scope_violation"] = sorted(set(plan.tables) - allowed)
                plan = QueryPlan(
                    intent="safe_failure",
                    output="text",
                    clarification_question="Khong the tao truy van an toan trong pham vi file dang chon.",
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
                    self.memory_service.save_turn(
                        state,
                        role="assistant",
                        content=started_clarification.summary or started_clarification.title,
                        execution_mode=started_clarification.metadata.get("execution_mode"),
                        query_plan=plan.model_dump(),
                    )
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
                title="Khong the hoan tat",
                summary="Khong the ket noi voi he thong xu ly." if not debug else str(exc),
                metadata={
                    "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
                    "active_file_id": state.active_file_id,
                    "active_file_name": state.active_file_name,
                    "file_scope_validated": False,
                },
            )
            self.memory_service.save_turn(state, role="assistant", content=response.summary, execution_mode="ERROR")
            return response

    def _preflight_file_scope(self, conversation_id: str, state, message: str, debug: bool, started: float) -> ChatResponse | None:
        if not state.active_file_id:
            return self._file_scope_response(
                conversation_id,
                "clarification",
                "Can chon file",
                "Vui long chon mot file Excel dang Ready truoc khi dat cau hoi ve du lieu.",
                "CLARIFICATION",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        record = find_uploaded_file(state.active_file_id)
        if not record:
            state.active_file_id = None
            state.active_file_name = None
            self.memory_service.save_state(state)
            return self._file_scope_response(
                conversation_id,
                "clarification",
                "File dang chon khong con ton tai",
                "File dang chon da bi xoa. Vui long chon lai mot file Ready.",
                "CLARIFICATION",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        state.active_file_name = str(record.get("filename") or state.active_file_name or "")
        if record.get("status") != "ready" or not record.get("queryable"):
            status = str(record.get("status") or "")
            summary = (
                "File dang duoc xu ly. Vui long doi den khi trang thai Ready roi hoi tiep."
                if status in {"uploaded", "uploading", "processing"}
                else "File dang chon chua query duoc. Vui long upload lai file hoac chon file khac."
            )
            return self._file_scope_response(
                conversation_id,
                "error",
                "File chua san sang",
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
                "Dang dung file khac",
                f"Cuoc hoi thoai nay dang dung file {state.active_file_name}. Neu muon hoi ve {other}, hay chon file do truoc.",
                "REFUSAL",
                debug,
                started,
                state,
                file_scope_validated=False,
            )
        return None

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
        chart = _chart_payload(raw_dataframe, plan, catalog) if raw_dataframe is not None and plan.output in {"bar", "horizontal_bar", "line", "pie"} else None
        dashboard = None
        if response_type == "dashboard" and raw_dataframe is not None:
            dashboard = DashboardPayload(cards=kpi_cards(raw_dataframe), table=table, chart=chart)
        downloads = [_download_payload(path) for path in [html_path, xlsx_path] if path and path.exists()]
        return ChatResponse(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            response_type=response_type,
            title=presented.title,
            summary=presented.summary,
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


def _chart_payload(df: pd.DataFrame, plan: QueryPlan, catalog: dict) -> ChartPayload | None:
    if df.empty or len(df.columns) < 2 or plan.output not in {"bar", "horizontal_bar", "line", "pie"}:
        return None
    x = plan.dimensions[0] if plan.dimensions and plan.dimensions[0] in df.columns else df.columns[0]
    y_candidates = [metric.name or f"{metric.aggregation}_{metric.column}" for metric in plan.metrics]
    y = next((column for column in y_candidates if column in df.columns), df.columns[-1])
    if y == x:
        y = next((column for column in df.columns if column != x), y)
    x_label = humanize_column_name(str(x), catalog)
    y_label = humanize_column_name(str(y), catalog)
    data = df[[x, y]].head(100).rename(columns={x: x_label, y: y_label}).to_dict(orient="records")
    return ChartPayload(type=plan.output, title="Kết quả phân tích", x_key=x_label, y_keys=[y_label], data=_json_safe(data))


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
    return ConversationPayload(
        id=str(item.get("id", "")),
        title=_display_title(str(item.get("title") or "Cuoc tro chuyen")),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
        status=str(item.get("status") or "active"),
        active_file_id=getattr(state, "active_file_id", None),
        active_file_name=getattr(state, "active_file_name", None),
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
    chart_requested = any(term in q for term in ["bieu do", "chart", "ve "])
    overview_requested = any(term in q for term in ["tong quan", "overview"])
    has_grouping = any(term in q for term in ["theo", "may", "nguyen nhan", "nhom", "cong"])
    has_metric = any(term in q for term in ["downtime", "thoi gian", "thoi luong", "so lan", "dem", "count"])
    return chart_requested and overview_requested and not (has_grouping or has_metric)


def _ascii_text(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))
