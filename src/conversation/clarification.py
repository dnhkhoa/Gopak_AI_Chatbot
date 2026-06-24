from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.application.schemas import ChatResponse
from src.conversation.state import ConversationState, PendingClarification
from src.query.schemas import MetricSpec, QueryPlan, SortSpec
from src.query_understanding.catalog_utils import find_table, role_column
from src.query_understanding.text import normalize_text


@dataclass
class ClarificationResolution:
    response: ChatResponse | None = None
    resolved_message: str | None = None
    resolution: str = "NONE"


class ClarificationResolver:
    def __init__(self, catalog: dict):
        self.catalog = catalog

    def resolve_pending(
        self,
        conversation_id: str,
        message: str,
        state: ConversationState,
        *,
        debug: bool,
        started: float,
    ) -> ClarificationResolution:
        pending = state.pending_clarification
        if pending is None:
            return ClarificationResolution()
        q = normalize_text(message)
        if _is_new_topic(q) and not _is_slot_answer(q):
            state.pending_clarification = None
            return ClarificationResolution(resolution="UNRELATED_NEW_TOPIC")

        slots = dict(pending.resolved_slots)
        if "limit" in pending.missing_slots:
            limit = _extract_int(q)
            if limit is not None:
                slots["limit"] = max(1, min(limit, 50))
        if "metric" in pending.missing_slots:
            metric = _metric_from_text(q)
            if metric:
                slots["metric"] = metric
        if "dimension" in pending.missing_slots:
            dimension = _dimension_from_text(q)
            if dimension:
                slots["dimension"] = dimension
        if "output" in pending.missing_slots:
            output = _output_from_text(q)
            if output:
                slots["output"] = output

        missing = [slot for slot in pending.missing_slots if slot not in slots]
        if missing:
            pending.attempts += 1
            pending.resolved_slots = slots
            pending.missing_slots = missing
            pending.last_question = _question_for_slot(missing[0], slots, pending)
            state.pending_clarification = pending
            return ClarificationResolution(
                response=self._clarification_response(conversation_id, pending.last_question, state, debug, started, "PARTIAL"),
                resolution="PARTIAL",
            )

        state.pending_clarification = None
        resolved_message = _compose_resolved_message(pending, slots)
        state.resolved_request = {"resolution": "COMPLETE", "message": resolved_message, "slots": slots}
        return ClarificationResolution(resolved_message=resolved_message, resolution="COMPLETE")

    def maybe_start(
        self,
        conversation_id: str,
        message: str,
        state: ConversationState,
        plan: QueryPlan,
        *,
        debug: bool,
        started: float,
    ) -> ChatResponse | None:
        if plan.intent != "clarification" or not state.active_file_id:
            return None
        q = normalize_text(message)
        kind = _pending_kind(q, plan.clarification_question or "")
        if kind is None:
            return None
        pending = _build_pending(state.active_file_id, message, kind)
        state.pending_clarification = pending
        return self._clarification_response(conversation_id, pending.last_question, state, debug, started, "START")

    def _clarification_response(
        self,
        conversation_id: str,
        question: str,
        state: ConversationState,
        debug: bool,
        started: float,
        resolution: str,
    ) -> ChatResponse:
        metadata = {
            "execution_mode": "CLARIFICATION",
            "router_confidence": 1.0,
            "routing_reason": "pending_clarification",
            "llm_called": False,
            "llm_call_count": 0,
            "generated_sql": None,
            "pending_clarification_after": state.pending_clarification.model_dump() if state.pending_clarification else None,
            "clarification_resolution": resolution,
            "active_file_id": state.active_file_id,
            "active_file_name": state.active_file_name,
            "file_scope_validated": bool(state.active_file_id),
            "latency_ms": {"total": round((perf_counter() - started) * 1000, 1)},
            "debug": {"state_after": state.model_dump()} if debug else None,
        }
        return ChatResponse(
            message_id="pending-clarification",
            conversation_id=conversation_id,
            response_type="clarification",
            title="Cần làm rõ",
            summary=question,
            metadata=metadata,
        )


def build_plan_from_resolved_message(catalog: dict, state: ConversationState, message: str) -> QueryPlan | None:
    q = normalize_text(message)
    scoped_tables = catalog.get("tables") or []
    table = scoped_tables[0] if len(scoped_tables) == 1 else find_table(catalog, "machine_downtime") or (scoped_tables or [None])[0]
    if not table:
        return None
    duration = role_column(table, "duration_seconds")
    machine = role_column(table, "machine")
    loss_name = role_column(table, "loss_name")
    loss_group = role_column(table, "loss_group")
    metric_name = "row_count" if "so lan" in q or "ban ghi" in q or "count" in q else "total_duration_seconds"
    metric = (
        {"aggregation": "count", "column": None, "name": "row_count"}
        if metric_name == "row_count" or not duration
        else {"aggregation": "sum", "column": duration, "name": "total_duration_seconds"}
    )
    dimension = machine if "may" in q else loss_name if "nguyen nhan" in q or "loi" in q else loss_group if "nhom" in q else None
    output = "bar" if any(term in q for term in ["bieu do", "chart", "ve cot", "ve line", "ve chart", "ve bieu do"]) else "table"
    intent = "chart" if output == "bar" else "query"
    limit = _extract_int(q) or (5 if "top" in q else 20)
    if not metric["column"] and metric["aggregation"] != "count":
        return None
    return QueryPlan(
        intent=intent,
        tables=[table["table_name"]],
        dimensions=[dimension] if dimension else [],
        metrics=[metric],
        sort=[{"column": metric["name"], "direction": "desc"}] if dimension else [],
        limit=limit,
        output=output,
    )


def restore_topic_plan(catalog: dict, state: ConversationState, message: str) -> QueryPlan | None:
    q = normalize_text(message)
    if not any(term in q for term in ["quay lai", "luc nay", "truoc do", "nhu tren", "ban dau"]):
        return None
    allowed_tables = {table["table_name"] for table in catalog.get("tables", [])}
    frames = [
        item
        for item in reversed(state.topic_frames or [])
        if item.get("active_file_id") == state.active_file_id and item.get("last_query_plan")
    ]
    for frame in frames:
        try:
            plan = QueryPlan.model_validate(frame["last_query_plan"])
        except Exception:
            continue
        if not plan.tables or not set(plan.tables).issubset(allowed_tables):
            continue
        label = normalize_text(str(frame.get("label") or ""))
        if "may" in q and "may" not in label and "machine" not in label:
            continue
        if "nguyen nhan" in q and "nguyen nhan" not in label and "loss" not in label:
            continue
        _apply_topic_delta(plan, catalog, q)
        return plan
    return None


def _apply_topic_delta(plan: QueryPlan, catalog: dict, q: str) -> None:
    table = next((item for item in catalog.get("tables", []) if item["table_name"] in plan.tables), None)
    duration = role_column(table, "duration_seconds") if table else None
    if any(term in q for term in ["so lan", "dem", "count", "lan dung"]):
        plan.metrics = [MetricSpec(aggregation="count", column=None, name="row_count")]
        if plan.dimensions:
            plan.sort = [SortSpec(column="row_count", direction="desc")]
    elif any(term in q for term in ["tong", "downtime", "thoi gian", "thoi luong"]) and duration:
        plan.metrics = [MetricSpec(aggregation="sum", column=duration, name="total_duration_seconds")]
        if plan.dimensions:
            plan.sort = [SortSpec(column="total_duration_seconds", direction="desc")]
    if any(term in q for term in ["bieu do", "chart", "ve cot", "ve line", "ve chart", "ve bieu do"]):
        plan.intent = "chart"
        plan.output = "bar"


def _pending_kind(q: str, clarification: str) -> str | None:
    if _looks_complete(q):
        return None
    text = q + " " + normalize_text(clarification)
    if q in {"top", "top may", "top nguyen nhan"} or "top bao nhieu" in text:
        return "top"
    if any(term in q for term in ["bieu do", "chart", "ve cot", "ve line", "ve chart", "ve bieu do", "tong quan"]):
        return "chart_overview"
    if "ban muon hoi ve tong" in text or "metric" in text:
        return "metric_dimension"
    return None


def _looks_complete(q: str) -> bool:
    has_metric = _metric_from_text(q) is not None or "downtime" in q
    has_dimension = _dimension_from_text(q) is not None
    has_limit = _extract_int(q) is not None or any(term in q for term in ["top", "bottom"])
    if any(term in q for term in ["top", "bottom", "dung dau", "cao nhat", "nhieu nhat"]):
        return has_metric and has_dimension and has_limit
    if any(term in q for term in ["bieu do", "chart", "ve cot", "ve line", "ve chart", "ve bieu do"]):
        return has_metric and has_dimension
    return False


def _build_pending(active_file_id: str, message: str, kind: str) -> PendingClarification:
    if kind == "top":
        missing = ["limit", "dimension"]
        question = "Bạn muốn xem top bao nhiêu?"
        partial = {"operation": "top", "metric": "downtime"}
    elif kind == "chart_overview":
        missing = ["metric", "dimension"]
        question = "Bạn muốn biểu đồ tổng thời lượng hay số lần dừng?"
        partial = {"operation": "chart", "output": "bar"}
    else:
        missing = ["metric", "dimension"]
        question = "Bạn muốn tổng số bản ghi hay tổng thời lượng?"
        partial = {"operation": "query"}
    return PendingClarification(
        active_file_id=active_file_id,
        original_message=message,
        original_intent=kind,
        partial_request=partial,
        missing_slots=missing,
        allowed_metrics=["downtime", "count"],
        allowed_dimensions=["machine", "loss_name", "loss_group"],
        allowed_outputs=["table", "bar"],
        allowed_values={"limit": ["1..50"]},
        last_question=question,
    )


def _question_for_slot(slot: str, slots: dict[str, object], pending: PendingClarification) -> str:
    if slot == "limit":
        return "Bạn muốn xem top bao nhiêu?"
    if slot == "metric":
        return "Bạn muốn tổng số bản ghi hay tổng thời lượng?"
    if slot == "dimension":
        if pending.original_intent == "chart_overview":
            return "Bạn muốn nhóm biểu đồ theo máy hay nguyên nhân?"
        return "Bạn muốn nhóm kết quả theo máy hay nguyên nhân?"
    if slot == "output":
        return "Bạn muốn xem bảng hay biểu đồ?"
    return "Bạn muốn làm rõ phần nào?"


def _compose_resolved_message(pending: PendingClarification, slots: dict[str, object]) -> str:
    operation = pending.partial_request.get("operation")
    metric = str(slots.get("metric") or pending.partial_request.get("metric") or "downtime")
    dimension = str(slots.get("dimension") or "machine")
    limit = slots.get("limit")
    output = pending.partial_request.get("output") or slots.get("output")
    metric_text = "số lần dừng" if metric == "count" else "downtime"
    dim_text = "máy" if dimension == "machine" else "nguyên nhân" if dimension == "loss_name" else "nhóm nguyên nhân"
    if operation == "top":
        return f"top {limit or 5} {dim_text} theo {metric_text}"
    if operation == "chart":
        return f"vẽ biểu đồ tổng {metric_text} theo {dim_text}"
    if output == "bar":
        return f"vẽ biểu đồ tổng {metric_text} theo {dim_text}"
    return f"tổng {metric_text} theo {dim_text}"


def _metric_from_text(q: str) -> str | None:
    if any(term in q for term in ["so lan", "dem", "ban ghi", "count", "lan dung"]):
        return "count"
    if any(term in q for term in ["tong", "thoi luong", "thoi gian", "downtime", "may bi dung"]):
        return "downtime"
    return None


def _dimension_from_text(q: str) -> str | None:
    if "may" in q or "machine" in q:
        return "machine"
    if any(term in q for term in ["nguyen nhan", "loi", "su co"]):
        return "loss_name"
    if "nhom" in q:
        return "loss_group"
    return None


def _output_from_text(q: str) -> str | None:
    if "bieu do" in q or "chart" in q or "ve" in q:
        return "bar"
    if "bang" in q or "table" in q:
        return "table"
    return None


def _extract_int(q: str) -> int | None:
    import re

    match = re.search(r"\b(\d{1,2})\b", q)
    return int(match.group(1)) if match else None


def _is_new_topic(q: str) -> bool:
    semantic_new_request = any(
        term in q
        for term in [
            "schema",
            "cot nao",
            "du lieu mau",
            "noi dung data",
            "file co gi",
            "bo bieu do",
            "phan tich",
            "nhan xet",
            "giai thich",
            "so sanh",
            "top",
            "ty le",
            "ty trong",
            "phan tram",
            "quay lai",
        ]
    )
    return semantic_new_request


def _is_slot_answer(q: str) -> bool:
    words = q.strip().split()
    if len(words) > 6:
        return False
    return (
        _metric_from_text(q) is not None
        or _dimension_from_text(q) is not None
        or _output_from_text(q) is not None
        or _extract_int(q) is not None
    )
