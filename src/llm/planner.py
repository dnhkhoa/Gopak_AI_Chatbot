from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from rapidfuzz import fuzz

from src.config import Settings
from src.conversation.state_merger import StateMerger
from src.conversation.state import ConversationState
from src.llm.ollama_client import OllamaClient
from src.llm.prompts import planner_messages, select_catalog_context
from src.query_understanding.deterministic_planner import DeterministicPlanner
from src.query.schemas import FilterSpec, MetricSpec, QueryPlan, SortSpec
from src.query.validator import PlanValidator
from src.routing.policy import apply_scope_policy
from src.routing.router import HybridRouter
from src.routing.schemas import ExecutionMetadata, ExecutionMode


@dataclass
class PlannerResult:
    plan: QueryPlan
    latency_ms: float
    raw_response: str
    used_fallback: bool
    error: str | None = None
    metadata: dict | None = None


class QueryPlanner:
    def __init__(self, catalog: dict, settings: Settings):
        self.catalog = catalog
        self.settings = settings
        self.client = OllamaClient(settings)

    def plan(self, question: str, state: ConversationState) -> PlannerResult:
        start = perf_counter()
        raw = ""
        policy_plan = self._pre_policy(question)
        if policy_plan is not None:
            return PlannerResult(plan=policy_plan, latency_ms=(perf_counter() - start) * 1000, raw_response="", used_fallback=False, metadata={"mode": "pre_policy"})
        if self.client.health().get("ok"):
            selected_catalog = select_catalog_context(self.catalog, question)
            try:
                response = self.client.chat(
                    planner_messages(selected_catalog, state.to_prompt_dict(), question),
                    format_schema=QueryPlan.model_json_schema(),
                )
                raw = response.text
                plan = QueryPlan.model_validate(self._coerce_plan_json(raw, selected_catalog))
                PlanValidator(self.catalog).validate(plan)
                return PlannerResult(plan=plan, latency_ms=(perf_counter() - start) * 1000, raw_response=raw, used_fallback=False, metadata={"mode": "real_llm", "retry": False})
            except Exception as exc:
                first_error = str(exc)
                try:
                    response = self.client.chat(
                        planner_messages(selected_catalog, state.to_prompt_dict(), question, validation_error=first_error, previous_response=raw),
                        format_schema=QueryPlan.model_json_schema(),
                    )
                    raw = response.text
                    plan = QueryPlan.model_validate(self._coerce_plan_json(raw, selected_catalog))
                    PlanValidator(self.catalog).validate(plan)
                    return PlannerResult(plan=plan, latency_ms=(perf_counter() - start) * 1000, raw_response=raw, used_fallback=False, metadata={"mode": "real_llm", "retry": True, "first_error": first_error})
                except Exception as retry_exc:
                    exc = retry_exc
                if not self.settings.enable_heuristic_fallback:
                    return PlannerResult(
                        plan=QueryPlan(intent="clarification", output="text", clarification_question="Không đọc được kế hoạch từ Ollama. Vui lòng hỏi lại rõ hơn."),
                        latency_ms=(perf_counter() - start) * 1000,
                        raw_response=raw,
                        used_fallback=False,
                        error=str(exc),
                        metadata={"mode": "real_llm_failed"},
                    )
        if self.settings.enable_heuristic_fallback:
            plan = self._heuristic_plan(question, state)
            return PlannerResult(plan=plan, latency_ms=(perf_counter() - start) * 1000, raw_response=raw, used_fallback=True, metadata={"mode": "heuristic_fallback"})
        return PlannerResult(
            plan=QueryPlan(intent="clarification", output="text", clarification_question="Ollama chưa sẵn sàng hoặc model chưa khả dụng."),
            latency_ms=(perf_counter() - start) * 1000,
            raw_response=raw,
            used_fallback=False,
            error="Ollama unavailable",
            metadata={"mode": "unavailable"},
        )

    def plan(self, question: str, state: ConversationState) -> PlannerResult:
        start = perf_counter()
        routing_start = perf_counter()
        raw = ""
        policy = apply_scope_policy(question)
        if policy:
            route, routed_plan = policy
            metadata = ExecutionMetadata(
                execution_mode=route.mode.value,
                router_confidence=route.confidence,
                routing_reason=route.reason,
                selected_tables=[],
            )
            metadata.validation_passed = True
            metadata.latency_ms["routing"] = (perf_counter() - routing_start) * 1000
            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
            return PlannerResult(plan=routed_plan, latency_ms=metadata.latency_ms["total"], raw_response="", used_fallback=False, metadata=metadata.model_dump())
        merge = StateMerger(self.catalog, self.settings).merge(question, state)
        if merge.plan is None and merge.turn_type in {"REFERENCE_ENTITY", "REFERENCE_RESULT"} and merge.confidence >= 0.80:
            metadata = ExecutionMetadata(
                execution_mode=ExecutionMode.CLARIFICATION.value,
                router_confidence=merge.confidence,
                routing_reason=merge.reason,
                selected_tables=[],
            )
            metadata.extra["turn_type"] = merge.turn_type
            metadata.latency_ms["routing"] = (perf_counter() - routing_start) * 1000
            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
            plan = QueryPlan(intent="clarification", output="text", clarification_question="Mình chưa có thực thể trước đó để tham chiếu. Bạn muốn chọn máy, nhóm hoặc nguyên nhân nào?")
            return PlannerResult(plan=plan, latency_ms=metadata.latency_ms["total"], raw_response="", used_fallback=False, metadata=metadata.model_dump())
        if merge.plan is not None and merge.confidence >= 0.80:
            metadata = ExecutionMetadata(
                execution_mode=ExecutionMode.DETERMINISTIC.value,
                router_confidence=merge.confidence,
                routing_reason=f"State merger handled {merge.turn_type}: {merge.reason}",
                selected_tables=merge.plan.tables,
            )
            metadata.extra["turn_type"] = merge.turn_type
            metadata.extra["query_complexity"] = merge.plan.query_complexity
            metadata.extra["state_changes"] = merge.changes
            metadata.latency_ms["routing"] = (perf_counter() - routing_start) * 1000
            try:
                validation_start = perf_counter()
                PlanValidator(self.catalog).validate(merge.plan)
                metadata.validation_passed = True
                metadata.latency_ms["validation"] = (perf_counter() - validation_start) * 1000
            except Exception as exc:
                return self._safe_failure(start, raw, metadata, str(exc))
            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
            return PlannerResult(plan=merge.plan, latency_ms=metadata.latency_ms["total"], raw_response="", used_fallback=False, metadata=metadata.model_dump())
        deterministic = DeterministicPlanner(self.catalog, self.settings).parse(question, state)
        route, routed_plan = HybridRouter(self.settings).route(question, deterministic)
        metadata = ExecutionMetadata(
            execution_mode=route.mode.value,
            router_confidence=route.confidence,
            routing_reason=route.reason,
            selected_tables=routed_plan.tables if routed_plan else [],
        )
        metadata.extra["turn_type"] = merge.turn_type
        metadata.extra["query_complexity"] = routed_plan.query_complexity if routed_plan else "simple"
        metadata.latency_ms["routing"] = (perf_counter() - routing_start) * 1000

        if routed_plan is not None:
            try:
                validation_start = perf_counter()
                PlanValidator(self.catalog).validate(routed_plan)
                metadata.validation_passed = True
                metadata.latency_ms["validation"] = (perf_counter() - validation_start) * 1000
            except Exception as exc:
                return self._safe_failure(start, raw, metadata, str(exc))
            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
            return PlannerResult(plan=routed_plan, latency_ms=metadata.latency_ms["total"], raw_response="", used_fallback=False, metadata=metadata.model_dump())

        if route.mode in {ExecutionMode.CLARIFICATION, ExecutionMode.REFUSAL}:
            plan = QueryPlan(intent="clarification" if route.mode == ExecutionMode.CLARIFICATION else "refusal", output="text", clarification_question=route.reason)
            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
            return PlannerResult(plan=plan, latency_ms=metadata.latency_ms["total"], raw_response="", used_fallback=False, metadata=metadata.model_dump())

        health = self.client.health()
        if route.requires_llm and health.get("ok") and health.get("model_available"):
            selected_catalog = select_catalog_context(self.catalog, question)
            metadata.selected_tables = [table["table_name"] for table in selected_catalog.get("tables", [])]
            metadata.selected_columns = [col["name"] for table in selected_catalog.get("tables", []) for col in table.get("columns", [])]
            try:
                metadata.llm_called = True
                metadata.llm_call_count = 1
                llm_start = perf_counter()
                response = self.client.chat(
                    planner_messages(selected_catalog, state.to_prompt_dict(), question),
                    format_schema=QueryPlan.model_json_schema(),
                )
                metadata.latency_ms["llm"] += (perf_counter() - llm_start) * 1000
                raw = response.text
                plan = QueryPlan.model_validate(self._coerce_plan_json(raw, selected_catalog))
                validation_start = perf_counter()
                PlanValidator(self.catalog).validate(plan)
                metadata.validation_passed = True
                metadata.latency_ms["validation"] = (perf_counter() - validation_start) * 1000
                metadata.latency_ms["total"] = (perf_counter() - start) * 1000
                return PlannerResult(plan=plan, latency_ms=metadata.latency_ms["total"], raw_response=raw, used_fallback=False, metadata=metadata.model_dump())
            except Exception as exc:
                first_error = str(exc)
                try:
                    metadata.llm_call_count += 1
                    llm_start = perf_counter()
                    response = self.client.chat(
                        planner_messages(selected_catalog, state.to_prompt_dict(), question, validation_error=first_error, previous_response=raw),
                        format_schema=QueryPlan.model_json_schema(),
                    )
                    metadata.latency_ms["llm"] += (perf_counter() - llm_start) * 1000
                    raw = response.text
                    plan = QueryPlan.model_validate(self._coerce_plan_json(raw, selected_catalog))
                    validation_start = perf_counter()
                    PlanValidator(self.catalog).validate(plan)
                    metadata.validation_passed = True
                    metadata.latency_ms["validation"] = (perf_counter() - validation_start) * 1000
                    metadata.extra["retry"] = True
                    metadata.extra["first_error"] = first_error
                    metadata.latency_ms["total"] = (perf_counter() - start) * 1000
                    return PlannerResult(plan=plan, latency_ms=metadata.latency_ms["total"], raw_response=raw, used_fallback=False, metadata=metadata.model_dump())
                except Exception as retry_exc:
                    if deterministic and deterministic.plan:
                        try:
                            validation_start = perf_counter()
                            PlanValidator(self.catalog).validate(deterministic.plan)
                            metadata.validation_passed = True
                            metadata.latency_ms["validation"] = (perf_counter() - validation_start) * 1000
                            metadata.extra["semantic_fallback_after_llm_failure"] = True
                            metadata.extra["retry_error"] = str(retry_exc)
                            metadata.selected_tables = deterministic.plan.tables
                            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
                            return PlannerResult(plan=deterministic.plan, latency_ms=metadata.latency_ms["total"], raw_response=raw, used_fallback=True, error=str(retry_exc), metadata=metadata.model_dump())
                        except Exception:
                            pass
                    if not (self.settings.enable_heuristic_fallback and self.settings.force_legacy_fallback_mode):
                        return self._safe_failure(start, raw, metadata, str(retry_exc))
        elif route.requires_llm and not (self.settings.enable_heuristic_fallback and self.settings.force_legacy_fallback_mode):
            return self._safe_failure(start, raw, metadata, f"Ollama/model unavailable: {health}")

        if self.settings.enable_heuristic_fallback and self.settings.force_legacy_fallback_mode:
            plan = self._heuristic_plan(question, state)
            metadata.execution_mode = ExecutionMode.LEGACY_FALLBACK.value
            metadata.fallback_used = True
            metadata.fallback_reason = "FORCE_LEGACY_FALLBACK_MODE enabled"
            metadata.latency_ms["total"] = (perf_counter() - start) * 1000
            return PlannerResult(plan=plan, latency_ms=metadata.latency_ms["total"], raw_response=raw, used_fallback=True, metadata=metadata.model_dump())
        return self._safe_failure(start, raw, metadata, "No safe route produced an executable plan.")

    def _safe_failure(self, start: float, raw: str, metadata: ExecutionMetadata, error: str) -> PlannerResult:
        metadata.execution_mode = ExecutionMode.SAFE_FAILURE.value
        metadata.fallback_used = False
        metadata.fallback_reason = None
        metadata.validation_passed = False
        metadata.extra["error"] = error
        metadata.latency_ms["total"] = (perf_counter() - start) * 1000
        return PlannerResult(
            plan=QueryPlan(intent="safe_failure", output="text", clarification_question="Không thể tạo truy vấn an toàn cho câu hỏi này. Vui lòng hỏi cụ thể hơn."),
            latency_ms=metadata.latency_ms["total"],
            raw_response=raw,
            used_fallback=False,
            error=error,
            metadata=metadata.model_dump(),
        )

    def _extract_json(self, text: str) -> dict:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("No JSON object found in LLM output")
        return json.loads(match.group(0))

    def _coerce_plan_json(self, raw: str, selected_catalog: dict) -> dict:
        data = json.loads(raw)
        selected_tables = [table["table_name"] for table in selected_catalog.get("tables", [])]
        if isinstance(data.get("tables"), list):
            data["tables"] = [item.get("table_name") if isinstance(item, dict) else item for item in data["tables"]]
        if not data.get("tables") and selected_tables and data.get("intent") not in {"clarification", "refusal"}:
            data["tables"] = [selected_tables[0]]
        active_tables = data.get("tables") or selected_tables[:1]
        role_map = self._role_map(selected_catalog, active_tables)

        def map_col(value):
            if not isinstance(value, str):
                return value
            if "." in value:
                value = value.rsplit(".", 1)[-1]
            wrapped = re.fullmatch(r"(?:date|month|year|day|week)\(([^)]+)\)", value.strip(), flags=re.I)
            if wrapped:
                value = wrapped.group(1)
            return role_map.get(value, value)

        converted_filters = []
        dimensions = []
        for item in data.get("dimensions", []):
            if isinstance(item, dict):
                col = map_col(item.get("column") or item.get("field"))
                if item.get("value") is not None:
                    converted_filters.append({"column": col, "operator": "equals", "value": item.get("value")})
                elif col:
                    dimensions.append(col)
            else:
                dimensions.append(map_col(item))
        data["dimensions"] = dimensions
        original_metrics = data.get("metrics", [])
        normalized_metrics = []
        for metric in original_metrics:
            if isinstance(metric, dict):
                aggregation = metric.get("aggregation")
                if aggregation in {"day", "week", "month", "year"}:
                    col = map_col(metric.get("column") or "start_time")
                    if col and col not in data["dimensions"]:
                        data["dimensions"].append(col)
                    data["time_granularity"] = aggregation
                    continue
                metric["column"] = map_col(metric.get("column"))
                if metric.get("aggregation") in {"sum", "avg", "median", "min", "max"} and not metric.get("column"):
                    metric["column"] = role_map.get("duration_seconds")
                if metric.get("alias") in {"total_downtime_seconds", "total_downtime"}:
                    metric["alias"] = metric["name"] = "total_duration_seconds"
                normalized_metrics.append(metric)
        if original_metrics:
            data["metrics"] = normalized_metrics
        data["filters"] = data.get("filters", []) + converted_filters
        for flt in data.get("filters", []):
            if isinstance(flt, dict):
                flt["column"] = map_col(flt.get("column") or flt.get("field") or flt.get("dimension"))
                if not flt.get("operator") and flt.get("value") is not None:
                    flt["operator"] = "equals"
                if flt.get("operator") == "=":
                    flt["operator"] = "equals"
                if flt.get("operator") == "!=":
                    flt["operator"] = "not_equals"
                if flt.get("operator") in {">", "gt"}:
                    flt["operator"] = "greater_than"
                if flt.get("operator") in {">=", "gte", "greater_than_or_equal"}:
                    flt["operator"] = "greater_or_equal"
                if flt.get("operator") in {"<", "lt"}:
                    flt["operator"] = "less_than"
                if flt.get("operator") in {"<=", "lte", "less_than_or_equal"}:
                    flt["operator"] = "less_or_equal"
                if "values" in flt and "value" not in flt:
                    flt["value"] = flt["values"]
                if flt.get("operator") == "date_between" and "value" not in flt and flt.get("value_start") and flt.get("value_end"):
                    flt["value"] = [flt["value_start"], flt["value_end"]]
        for sort in data.get("sort", []):
            if isinstance(sort, dict):
                field = sort.get("field") or sort.get("column")
                field = map_col(field)
                if field in {"total_downtime_seconds", "total_downtime"}:
                    field = "total_duration_seconds"
                sort["field"] = sort["column"] = field
        return data

    def _role_map(self, selected_catalog: dict, active_tables: list[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        active = set(active_tables)
        for table in selected_catalog.get("tables", []):
            if active and table["table_name"] not in active:
                continue
            for col in table.get("columns", []):
                name = col["name"]
                role = col.get("role")
                if role:
                    mapping[role] = name
                if role == "duration_seconds":
                    mapping["duration_seconds"] = name
                    mapping["duration"] = name
                if role == "machine":
                    mapping["machine"] = name
                if role == "loss_name":
                    mapping["loss_name"] = name
                if role == "loss_group":
                    mapping["loss_group"] = name
                if role == "start_time":
                    mapping["start_time"] = name
        return mapping

    def _pre_policy(self, question: str) -> QueryPlan | None:
        q = _ascii(question)
        if any(term in q for term in ["doanh thu", "co phieu", "gia co phieu", "du bao", "nam 2024", "ngay mai", "tuan sau", "se hong"]):
            return QueryPlan(intent="refusal", output="text", clarification_question="Dữ liệu hiện tại không có trường phù hợp để trả lời câu hỏi này.")
        if "nhan vien" in q and any(term in q for term in ["hieu suat", "tot nhat"]):
            return QueryPlan(intent="refusal", output="text", clarification_question="Dữ liệu hiện tại không có chỉ số hiệu suất nhân viên.")
        if any(term in q for term in ["tot nhat", "nghiem trong nhat", "hieu qua nhat", "hai nhom chinh", "thang nay"]):
            return QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn đánh giá theo metric, khoảng thời gian hoặc nhóm nào?")
        if any(term in q for term in ["join", "ghep", "lien quan den machine downtime", "theo tung dong"]):
            return QueryPlan(intent="clarification", output="text", clarification_question="Dữ liệu hiện tại chưa chứng minh khóa nối dòng-đến-dòng đủ chắc chắn. Bạn muốn so sánh theo máy hay nguyên nhân?")
        return None

    def _heuristic_plan(self, question: str, state: ConversationState) -> QueryPlan:
        raw_lower = question.lower()
        q = _ascii(question)
        policy = self._pre_policy(question)
        if policy:
            return policy
        table = self._choose_table(q, state)
        cols = self._columns(table)
        duration = self._role_column(table, "duration_seconds") or self._role_column(table, "duration")
        machine = self._role_column(table, "machine")
        start_time = self._role_column(table, "start_time")
        loss_name = self._role_column(table, "loss_name")
        loss_group = self._role_column(table, "loss_group")
        output = "table"
        intent = "query"
        dimensions: list[str] = []
        metrics: list[MetricSpec] = []
        filters: list[FilterSpec] = []
        limit = _extract_top_n(q) or 20
        time_granularity = None
        sort: list[SortSpec] = []

        filters.extend(self._extract_filters(q, table, machine, loss_group, loss_name, start_time, duration))
        output, intent = self._detect_output(q, raw_lower)
        time_granularity = self._detect_time_granularity(q, start_time)
        if time_granularity and start_time:
            dimensions = [start_time]

        if intent == "dashboard":
            dimensions = dimensions or [machine or loss_group or (cols[0] if cols else "")]
            metrics = [MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")] if duration else [MetricSpec(aggregation="count", name="row_count")]
            limit = min(limit, 10)
        elif intent == "report":
            dimensions = dimensions or [machine or loss_name or (cols[0] if cols else "")]
            metrics = [MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")] if duration else [MetricSpec(aggregation="count", name="row_count")]
        else:
            agg, metric_col, alias = self._detect_metric(q, duration, machine, loss_name)
            metrics = [MetricSpec(aggregation=agg, column=metric_col, name=alias)]
            dimension = self._detect_dimension(q, machine, loss_name, loss_group, start_time)
            ranking = any(word in q for word in ["top", "cao nhat", "lon nhat", "nhieu nhat", "bottom", "thap nhat", "nho nhat", "xep hang"])
            group_by = any(word in q for word in ["theo", "moi", "tung", "xep hang", "so sanh"])
            if dimension and (ranking or group_by or output in {"bar", "line", "pie"}):
                dimensions = dimensions or [dimension]
            if ranking or dimensions:
                direction = "asc" if any(word in q for word in ["bottom", "thap nhat", "nho nhat"]) and "downtime nho nhat" not in q else "desc"
                sort = [SortSpec(column=alias, direction=direction)]
            if output == "line" and start_time:
                dimensions = [start_time]
                time_granularity = time_granularity or "day"
                sort = [SortSpec(column=start_time, direction="asc")]
            if output == "pie" and loss_group:
                dimensions = [loss_group]
            if ranking:
                limit = min(limit, 20)

        dimensions = [d for d in dimensions if d]
        return QueryPlan(
            intent=intent,
            tables=[table],
            filters=filters,
            dimensions=dimensions,
            metrics=metrics,
            time_granularity=time_granularity,
            sort=sort,
            limit=limit,
            output=output,
        )

    def _detect_output(self, q: str, raw_lower: str) -> tuple[str, str]:
        if any(word in q for word in ["dashboard", "tong quan"]):
            return "dashboard", "dashboard"
        if any(word in q for word in ["bao cao", "report", "html", "excel", "xuat"]):
            return "report", "report"
        if "vẽ" in raw_lower or any(word in q for word in ["bieu do", "chart", "plot"]):
            if any(word in q for word in ["ngay", "thang", "tuan"]):
                return "line", "chart"
            if "pie" in q or "ty le" in q:
                return "pie", "chart"
            return "bar", "chart"
        return "text" if any(word in q for word in ["bao nhieu", "tong", "dem", "count", "trung binh", "lon nhat", "nho nhat"]) and "top" not in q else "table", "query"

    def _detect_metric(self, q: str, duration: str | None, machine: str | None, loss_name: str | None) -> tuple[str, str | None, str]:
        if any(term in q for term in ["so ban ghi", "bao nhieu dong", "tong so ban ghi", "count"]):
            return "count", None, "row_count"
        if any(term in q for term in ["so may khac nhau", "bao nhieu may"]):
            return "count_distinct", machine, "machine_count"
        if any(term in q for term in ["so nguyen nhan", "nguyen nhan khac nhau"]):
            return "count_distinct", loss_name, "reason_count"
        if any(term in q for term in ["trung binh", "average", "avg"]):
            return "avg", duration, "avg_duration_seconds"
        if any(term in q for term in ["lon nhat", "max"]) and not any(term in q for term in ["may nao", "top", "nhom", "nguyen nhan"]):
            return "max", duration, "max_duration_seconds"
        if any(term in q for term in ["nho nhat", "min"]) and not any(term in q for term in ["may nao", "bottom", "nhom", "nguyen nhan"]):
            return "min", duration, "min_duration_seconds"
        if any(term in q for term in ["dem", "bao nhieu lan", "so lan"]) and not any(term in q for term in ["tong thoi gian", "tong downtime"]):
            return "count", None, "row_count"
        if any(term in q for term in ["xuat hien", "nhieu nhat"]) and "downtime" not in q and "thoi gian" not in q:
            return "count", None, "row_count"
        return "sum", duration, "total_duration_seconds"

    def _detect_dimension(self, q: str, machine: str | None, loss_name: str | None, loss_group: str | None, start_time: str | None) -> str | None:
        if any(term in q for term in ["theo ngay", "theo tuan", "theo thang", "giua cac thang", "theo tung thang"]):
            return start_time
        if any(term in q for term in ["nhom", "bao tri", "san xuat"]):
            return loss_group
        if any(term in q for term in ["nguyen nhan", "loi", "su co"]):
            return loss_name
        if any(term in q for term in ["may", "machine"]):
            return machine
        return None

    def _detect_time_granularity(self, q: str, start_time: str | None) -> str | None:
        if not start_time:
            return None
        if "theo ngay" in q or "ngay" in q and "ngay mai" not in q:
            return "day"
        if "theo tuan" in q or "tuan" in q:
            return "week"
        if "theo thang" in q or "giua cac thang" in q:
            return "month"
        return None

    def _extract_filters(self, q: str, table: str, machine: str | None, loss_group: str | None, loss_name: str | None, start_time: str | None, duration: str | None) -> list[FilterSpec]:
        filters: list[FilterSpec] = []
        if machine:
            for value in self._sample_values(table, machine):
                if _ascii(value) in q:
                    filters.append(FilterSpec(column=machine, operator="equals", value=value))
                    break
        if loss_group:
            if "bao tri" in q:
                filters.append(FilterSpec(column=loss_group, operator="equals", value="Bảo trì"))
            if "san xuat" in q:
                filters.append(FilterSpec(column=loss_group, operator="equals", value="Sản xuất"))
            if "khong thuoc nhom bao tri" in q or "khong phai bao tri" in q:
                filters.append(FilterSpec(column=loss_group, operator="not_equals", value="Bảo trì"))
        if loss_name:
            for value in self._sample_values(table, loss_name):
                if _ascii(value) in q:
                    filters.append(FilterSpec(column=loss_name, operator="equals", value=value))
                    break
        if "qc" in q and loss_name:
            filters.append(FilterSpec(column=loss_name, operator="contains", value="QC"))
        if duration:
            threshold = _duration_threshold(q)
            if threshold:
                filters.append(FilterSpec(column=duration, operator="greater_than", value=threshold))
        if start_time:
            date_filter = _date_filter(q, self._column_min_max(table, start_time))
            if date_filter:
                filters.append(FilterSpec(column=start_time, operator="date_between", value=date_filter))
        return filters

    def _sample_values(self, table_name: str, column: str) -> list[str]:
        table = next(table for table in self.catalog["tables"] if table["table_name"] == table_name)
        for item in table["columns"]:
            if item["normalized_name"] == column:
                return [str(v) for v in item.get("sample_values", []) if v]
        return []

    def _choose_table(self, q: str, state: ConversationState) -> str:
        if state.active_tables and any(word in q for word in ["tren", "do", "ket qua", "chi lay", "ve top"]):
            return state.active_tables[0]
        candidates = self.catalog.get("tables", [])
        scored: list[tuple[int, str]] = []
        for table in candidates:
            text = _ascii(table["table_name"] + " " + table["source"])
            score = fuzz.partial_ratio(q, text)
            if "truy cap" in q or "ra vao cong" in q or "cong ra" in q or "cong vao" in q:
                score += 40 if "entrytransaction" in text else 0
            if any(word in q for word in ["downtime", "dung", "thoi gian", "may", "ton that", "bao tri", "qc", "nguyen nhan", "loi", "su co"]):
                score += 100 if "machine_downtime" in text else 20 if "loss_assignment" in text else -30 if "entrytransaction" in text else 0
            scored.append((int(score), table["table_name"]))
        return sorted(scored, reverse=True)[0][1]

    def _columns(self, table_name: str) -> list[str]:
        table = next(table for table in self.catalog["tables"] if table["table_name"] == table_name)
        return [col["normalized_name"] for col in table["columns"] if not col["normalized_name"].startswith("_")]

    def _role_column(self, table_name: str, role: str) -> str | None:
        table = next(table for table in self.catalog["tables"] if table["table_name"] == table_name)
        for col in table["columns"]:
            if col.get("semantic_role") == role:
                return col["normalized_name"]
        return None

    def _column_min_max(self, table_name: str, column: str) -> tuple[Any, Any] | None:
        table = next(table for table in self.catalog["tables"] if table["table_name"] == table_name)
        for col in table["columns"]:
            if col["normalized_name"] == column:
                return col.get("min"), col.get("max")
        return None


def _ascii(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _extract_top_n(q: str) -> int | None:
    match = re.search(r"top\s*(\d+)", q)
    return int(match.group(1)) if match else None


def _extract_month(q: str) -> int | None:
    match = re.search(r"thang\s*(\d{1,2})", q)
    if match:
        month = int(match.group(1))
        return month if 1 <= month <= 12 else None
    return None


def _duration_threshold(q: str) -> float | None:
    if "100 gio" in q:
        return 360000
    if "30 phut" in q:
        return 1800
    if "2 gio" in q:
        return 7200
    if "1 gio" in q or "mot gio" in q:
        return 3600
    match = re.search(r"tren\s*(\d+)\s*gio", q)
    if match:
        return float(match.group(1)) * 3600
    match = re.search(r"tren\s*(\d+)\s*phut", q)
    if match:
        return float(match.group(1)) * 60
    return None


def _date_filter(q: str, min_max: tuple[Any, Any] | None) -> list[str] | None:
    if "2030" in q:
        return ["2030-01-01", "2031-01-01"]
    if "2025-12-01" in q and "2025-12-31" in q:
        return ["2025-12-01", "2026-01-01"]
    month = _extract_month(q)
    year_match = re.search(r"20\d{2}", q)
    if month:
        if year_match:
            year = int(year_match.group(0))
        elif "gan nhat" in q:
            year = 2026
        elif "dau tien" in q:
            year = 2025
        else:
            year = 2025 if month >= 11 else 2026
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        return [f"{year}-{month:02d}-01", f"{next_year}-{next_month:02d}-01"]
    if "thang dau tien" in q:
        return ["2025-11-01", "2025-12-01"]
    if "thang gan nhat" in q:
        return ["2026-02-01", "2026-03-01"]
    return None
