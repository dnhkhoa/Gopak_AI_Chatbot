from __future__ import annotations

from src.application.chat_service import _ascii_text, _is_open_ended_dataset_analysis
from src.application.turn_contracts import build_request_contract


def test_data_nay_open_ended_routes_to_semantic_analysis() -> None:
    question = (
        "Coi thu trong data nay co dieu gi bat thuong hoac dang quan tam, "
        "giai thich de hieu giup toi."
    )
    normalized = _ascii_text(question)
    assert _is_open_ended_dataset_analysis(normalized)


def test_negated_chart_phrase_does_not_request_chart_contract() -> None:
    question = "Bo bieu do di, phan tich ba nguyen nhan pho bien nhat va giai thich ket qua."
    contract = build_request_contract(question, source_file_id="machine", has_previous_result=True)
    assert contract.intent != "chart"
    assert "chart" not in contract.requested_outputs
    assert contract.requested_chart_type is None
    assert contract.relation_to_previous_turn == "NEW_REQUEST"


def test_about_phrase_ve_luong_xe_is_not_chart_request() -> None:
    question = "Cho toi mot insight ngan ve luong xe ra vao cong"
    contract = build_request_contract(question, source_file_id="entry", has_previous_result=False)
    assert contract.intent == "commentary"
    assert "chart" not in contract.requested_outputs
    assert contract.requested_chart_type is None


def test_short_context_refinements_keep_previous_plan() -> None:
    examples = [
        "Chi lay thang gan nhat",
        "Ch\u1ec9 l\u1ea5y th\u00e1ng g\u1ea7n nh\u1ea5t",
        "Ve bieu do cot",
        "V\u1ebd bi\u1ec3u \u0111\u1ed3 c\u1ed9t",
        "Doi thanh top 3",
        "Quay lai cau dau tien",
    ]
    for question in examples:
        contract = build_request_contract(question, source_file_id="machine", has_previous_result=True)
        assert contract.relation_to_previous_turn == "REFINEMENT"
        assert "last_plan" in contract.inherited_fields
        assert contract.explicitly_reset_fields == []


def test_self_contained_chart_request_stays_new_request() -> None:
    question = "Ve bieu do line xu huong downtime theo ngay"
    contract = build_request_contract(question, source_file_id="machine", has_previous_result=True)
    assert contract.relation_to_previous_turn == "NEW_REQUEST"
    assert contract.intent == "chart"
    assert contract.requested_chart_type == "line"
