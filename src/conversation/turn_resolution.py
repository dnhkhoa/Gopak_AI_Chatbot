from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.conversation.state import ConversationState
from src.llm.semantic_contracts import TurnRelationship
from src.query_understanding.text import normalize_text


class TurnResolution(BaseModel):
    relationship: TurnRelationship
    referenced_artifact_id: str | None = None
    referenced_artifact_type: str | None = None
    inherited_fields: list[str] = Field(default_factory=list)
    reset_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    resolution_source: str = "deterministic_state_machine"
    attributes: dict[str, Any] = Field(default_factory=dict)


def resolve_turn_relationship(message: str, state: ConversationState) -> TurnResolution:
    q = normalize_text(message)
    last_type = state.last_visible_artifact_type
    last_id = state.last_visible_artifact_id
    has_report = bool(state.active_report_context)

    if _is_cancel(q):
        return TurnResolution(
            relationship=TurnRelationship.CANCEL,
            confidence=0.95,
            reset_fields=["pending_clarification"],
        )

    if state.pending_clarification is not None:
        if _looks_like_slot_answer(q) and not _looks_like_complete_new_request(q):
            return TurnResolution(
                relationship=TurnRelationship.CLARIFICATION_ANSWER,
                confidence=0.90,
                inherited_fields=["pending_clarification"],
                referenced_artifact_id=last_id,
                referenced_artifact_type=last_type,
            )
        return TurnResolution(
            relationship=TurnRelationship.NEW_REQUEST,
            confidence=0.88,
            reset_fields=["pending_clarification", "last_plan", "last_result"],
            resolution_source="pending_clarification_bypassed_by_new_request",
        )

    if has_report and _is_report_export(q):
        return TurnResolution(
            relationship=TurnRelationship.ARTIFACT_EXPORT,
            referenced_artifact_id=state.active_report_context.report_id,
            referenced_artifact_type="REPORT",
            inherited_fields=["active_report_context", "source_file"],
            confidence=0.96,
            attributes={"action": "export_pdf"},
        )

    if has_report and _is_report_revision(q):
        return TurnResolution(
            relationship=TurnRelationship.ARTIFACT_REVISION,
            referenced_artifact_id=state.active_report_context.report_id,
            referenced_artifact_type="REPORT",
            inherited_fields=["active_report_context", "source_file", "validated_report_payload"],
            reset_fields=["pending_clarification"],
            confidence=0.92,
            attributes={"detail_level": _revision_detail_level(q), "action": "revise_report"},
        )

    if last_id and _references_previous(q):
        return TurnResolution(
            relationship=TurnRelationship.FOLLOW_UP_QUESTION,
            referenced_artifact_id=last_id,
            referenced_artifact_type=last_type,
            inherited_fields=["referenced_artifact_payload"],
            confidence=0.82,
        )

    return TurnResolution(
        relationship=TurnRelationship.NEW_REQUEST,
        reset_fields=["metric", "dimension", "filter", "time_range", "chart_type", "pending_clarification"],
        confidence=0.78,
    )


def _is_cancel(q: str) -> bool:
    return any(term in q for term in ["bo qua", "huy", "cancel", "thoi khong", "bat dau lai"])


def _is_report_export(q: str) -> bool:
    return any(term in q for term in ["xuat pdf", "tai bao cao", "file pdf", "cho toi pdf", "download pdf", "pdf"]) and not _is_report_revision(q)


def _is_report_revision(q: str) -> bool:
    return any(
        term in q
        for term in [
            "chi tiet hon",
            "day du hon",
            "rut gon",
            "ngan gon",
            "compact",
            "them phan",
            "bo phu luc",
            "danh cho quan ly",
            "ban quan ly",
        ]
    )


def _revision_detail_level(q: str) -> str:
    if any(term in q for term in ["rut gon", "ngan gon", "compact", "1-2 trang", "1 den 2 trang"]):
        return "COMPACT"
    if any(term in q for term in ["chi tiet hon", "day du hon", "deep dive", "sau hon"]):
        return "DETAILED"
    return "STANDARD"


def _references_previous(q: str) -> bool:
    return any(
        term in q
        for term in [
            "ket qua vua roi",
            "ket qua tren",
            "ket qua nay",
            "ket qua moi",
            "du lieu tren",
            "nhan xet",
            "giai thich",
            "insight",
            "doi sang",
            "chuyen sang",
            "quay lai",
            "chi tiet hon",
        ]
    )


def _looks_like_slot_answer(q: str) -> bool:
    words = q.split()
    if len(words) > 7:
        return False
    return any(term in q for term in ["so lan", "tong", "downtime", "may", "nguyen nhan", "bang", "bieu do"]) or any(ch.isdigit() for ch in q)


def _looks_like_complete_new_request(q: str) -> bool:
    output = any(term in q for term in ["bao cao", "bieu do", "chart", "top", "schema", "du lieu mau", "phan tich"])
    metric = any(term in q for term in ["downtime", "dowtime", "so lan", "tong", "thoi gian", "thoi luong"])
    dimension = any(term in q for term in ["may", "nguyen nhan", "ngay", "thang", "xu huong"])
    return output and (metric or dimension)
