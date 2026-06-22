from __future__ import annotations

from src.query.schemas import QueryPlan
from src.query_understanding.text import normalize_text
from src.routing.schemas import ExecutionMode, RouteDecision


def apply_scope_policy(question: str) -> tuple[RouteDecision, QueryPlan] | None:
    q = normalize_text(question)
    refusal_terms = [
        "doanh thu",
        "co phieu",
        "gia co phieu",
        "du bao",
        "ngay mai",
        "tuan sau",
        "se hong",
    ]
    if any(term in q for term in refusal_terms):
        return (
            RouteDecision(ExecutionMode.REFUSAL, 0.99, "Question is outside supported historical Excel analytics scope."),
            QueryPlan(intent="refusal", output="text", clarification_question="Dữ liệu hiện tại không hỗ trợ câu hỏi này."),
        )
    if "thang nay" in q and any(term in q for term in ["bao cao", "report"]):
        return (
            RouteDecision(ExecutionMode.CLARIFICATION, 0.90, "Calendar-relative report request is ambiguous without a metric/group."),
            QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn báo cáo tháng này theo metric hoặc nhóm nào?"),
        )
    if "nhan vien" in q and any(term in q for term in ["hieu suat", "tot nhat"]):
        return (
            RouteDecision(ExecutionMode.REFUSAL, 0.98, "Employee performance metric is not present in the loaded data."),
            QueryPlan(intent="refusal", output="text", clarification_question="Dữ liệu hiện tại không có chỉ số hiệu suất nhân viên."),
        )
    join_terms = ["join", "ghep", "theo tung dong", "transaction lien quan", "ra vao cong", "cong ra vao"]
    if any(term in q for term in join_terms) and any(term in q for term in ["downtime", "machine", "may", "loss"]):
        return (
            RouteDecision(ExecutionMode.REFUSAL, 0.95, "Requested row-level join is not proven by catalog relationships."),
            QueryPlan(intent="refusal", output="text", clarification_question="Không có khóa nối dòng-đến-dòng đủ chắc chắn để thực hiện truy vấn này."),
        )
    vague_terms = ["tot nhat", "nghiem trong nhat", "hieu qua nhat", "hai nhom chinh"]
    if any(term in q for term in vague_terms):
        return (
            RouteDecision(ExecutionMode.CLARIFICATION, 0.85, "Question asks for a ranking without an explicit metric."),
            QueryPlan(intent="clarification", output="text", clarification_question="Bạn muốn đánh giá theo thời gian downtime, số lần dừng, hay một tiêu chí khác?"),
        )
    return None
