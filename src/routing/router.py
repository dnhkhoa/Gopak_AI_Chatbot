from __future__ import annotations

from src.config import Settings
from src.query.schemas import QueryPlan
from src.query_understanding.deterministic_planner import DeterministicParse
from src.query_understanding.text import normalize_text
from src.routing.policy import apply_scope_policy
from src.routing.schemas import ExecutionMode, RouteDecision


class HybridRouter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def route(self, question: str, candidate: DeterministicParse | None) -> tuple[RouteDecision, QueryPlan | None]:
        policy = apply_scope_policy(question)
        if policy:
            return policy
        if candidate and candidate.plan and candidate.confidence >= self.settings.deterministic_confidence_threshold:
            return (
                RouteDecision(ExecutionMode.DETERMINISTIC, candidate.confidence, candidate.reason, requires_llm=False),
                candidate.plan,
            )
        q = normalize_text(question)
        if candidate and candidate.plan and 0.60 <= candidate.confidence < self.settings.deterministic_confidence_threshold:
            semantic_or_complex = any(term in q for term in ["lien quan", "giong", "gan voi", "ben trong", "do", "ket qua", "dung dau"])
            if semantic_or_complex:
                return RouteDecision(ExecutionMode.REAL_LLM, candidate.confidence, "Candidate is not high confidence and needs semantic/context reasoning.", True), None
            return (
                RouteDecision(ExecutionMode.CLARIFICATION, candidate.confidence, "Deterministic parser found a partial plan but confidence is below threshold."),
                QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn phân tích theo metric, nhóm, máy hoặc khoảng thời gian nào?"),
            )
        if any(term in q for term in ["lien quan", "giong", "gan voi", "setup", "qc", "bao tri", "vat tu"]):
            return RouteDecision(ExecutionMode.REAL_LLM, candidate.confidence if candidate else 0.55, "Semantic category matching may require LLM/candidate reasoning.", True), None
        return (
            RouteDecision(ExecutionMode.CLARIFICATION, candidate.confidence if candidate else 0.0, "Not enough information to form a safe deterministic query."),
            QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn hỏi về tổng, đếm, top, thời gian, máy hay nguyên nhân nào?"),
        )
