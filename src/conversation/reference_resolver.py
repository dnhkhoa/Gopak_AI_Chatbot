from __future__ import annotations

from dataclasses import dataclass

from src.conversation.state import ConversationState
from src.query_understanding.text import normalize_text


@dataclass
class ResolvedReference:
    entity_type: str
    column: str
    value: object
    source: str


def resolve_reference(question: str, state: ConversationState) -> ResolvedReference | None:
    q = normalize_text(question)
    first_row = (state.last_result_summary or {}).get("first_row") or {}

    if any(term in q for term in ["may do", "may dung dau"]):
        value = state.last_entities.get("top_machine") or first_row.get("may")
        if value is not None:
            return ResolvedReference("machine", "may", value, "top_machine")

    if "nguyen nhan dung dau" in q:
        value = state.last_entities.get("top_loss_name") or first_row.get("ten_ton_that")
        if value is not None:
            return ResolvedReference("loss_name", "ten_ton_that", value, "top_loss_name")

    if any(term in q for term in ["nhom do", "nhom tren", "nhom dung dau"]):
        value = state.last_entities.get("top_group") or first_row.get("nhom_ton_that")
        if value is not None:
            return ResolvedReference("loss_group", "nhom_ton_that", value, "top_group")

    return None
