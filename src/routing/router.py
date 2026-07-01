from __future__ import annotations

from src.config import Settings
from src.query.schemas import QueryPlan
from src.query_understanding.deterministic_planner import DeterministicParse
from src.query_understanding.text import normalize_text
from src.routing.policy import apply_scope_policy
from src.routing.schemas import ExecutionMode, RouteDecision


def _needs_semantic_resolution(q: str) -> bool:
    exact_simple = {"schema", "du lieu mau", "file co gi", "top", "top may", "top nguyen nhan"}
    if q.strip(" ?.!;:") in exact_simple:
        return False
    semantic_terms = [
        "dua tren toan bo",
        "toan bo du lieu",
        "giai thich",
        "nhan xet",
        "phan tich",
        "so sanh",
        "gioi han",
        "ket luan",
        "lien quan",
        "giong",
        "gan voi",
        "ben trong",
        "setup",
        "qc",
        "bao tri",
        "vat tu",
        "dang chu y",
        "bat thuong",
        "lo nhat",
        "co ve",
        "hop ly",
        "luc nay",
        "truoc do",
        "nhu tren",
        "tuong tu",
        "cai do",
        "cai dau",
        "quan tam",
        "dong thoi",
        "hien thi them",
        "ty trong",
        "ty le",
        "phan tram",
        "dung dau",
        "ket qua",
        "quay lai",
        "them",
        "bo bieu do",
    ]
    return any(term in q for term in semantic_terms)


def _semantic_override(q: str) -> bool:
    return any(
        term in q
        for term in [
            "co ve",
            "dang chu y",
            "diem dang chu y",
            "bat thuong",
            "hop ly",
            "lo nhat",
            "gay van de",
            "giai thich",
            "nhan xet",
            "phan tich",
            "so sanh",
            "gioi han",
            "ket luan",
            "bo bieu do",
        ]
    )


def _multipart_requires_semantic(q: str) -> bool:
    requested_parts = 0
    requested_parts += int(any(term in q for term in ["top", "cao nhat", "nhieu nhat", "pho bien", "dung dau"]))
    requested_parts += int(any(term in q for term in ["them", "dong thoi", "kem", "va "]))
    requested_parts += int(any(term in q for term in ["ty le", "ty trong", "phan tram"]))
    requested_parts += int(any(term in q for term in ["nhan xet", "giai thich", "phan tich", "so sanh"]))
    requested_parts += int(any(term in q for term in ["so lan", "trung binh", "tong downtime", "tong thoi gian"]))
    return requested_parts >= 3


class HybridRouter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def route(self, question: str, candidate: DeterministicParse | None) -> tuple[RouteDecision, QueryPlan | None]:
        policy = apply_scope_policy(question)
        if policy:
            return policy
        q = normalize_text(question)
        if candidate and candidate.plan and candidate.confidence >= self.settings.deterministic_confidence_threshold:
            return (
                RouteDecision(ExecutionMode.DETERMINISTIC, candidate.confidence, candidate.reason, requires_llm=False),
                candidate.plan,
            )
        if _semantic_override(q) or _multipart_requires_semantic(q):
            confidence = candidate.confidence if candidate else 0.62
            return RouteDecision(ExecutionMode.REAL_LLM, confidence, "Semantic or multipart request requires REAL_LLM structured resolution.", True), None
        if candidate and candidate.plan and 0.60 <= candidate.confidence < self.settings.deterministic_confidence_threshold:
            if _needs_semantic_resolution(q):
                return RouteDecision(ExecutionMode.REAL_LLM, candidate.confidence, "Candidate is not high confidence and needs semantic/context reasoning.", True), None
            return (
                RouteDecision(ExecutionMode.CLARIFICATION, candidate.confidence, "Deterministic parser found a partial plan but confidence is below threshold."),
                QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn phân tích theo metric, nhóm, máy hoặc khoảng thời gian nào?"),
            )
        if _needs_semantic_resolution(q):
            return RouteDecision(ExecutionMode.REAL_LLM, candidate.confidence if candidate else 0.55, "Semantic category matching may require LLM/candidate reasoning.", True), None
        return (
            RouteDecision(ExecutionMode.CLARIFICATION, candidate.confidence if candidate else 0.0, "Not enough information to form a safe deterministic query."),
            QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn hỏi về tổng, đếm, top, thời gian, máy hay nguyên nhân nào?"),
        )
