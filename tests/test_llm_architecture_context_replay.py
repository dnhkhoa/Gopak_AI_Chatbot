from src.conversation.artifacts import ActiveReportContext
from src.conversation.state import ConversationState, PendingClarification
from src.conversation.turn_resolution import resolve_turn_relationship
from src.llm.semantic_contracts import TurnRelationship
from src.llm.semantic_resolver import build_resolver_input


def test_report_replay_keeps_artifact_context_for_export_after_restart_snapshot():
    state = ConversationState(
        active_file_id="downtime",
        active_report_context=ActiveReportContext(report_id="r1", root_report_id="r1", source_file_id="downtime"),
    )

    snapshot = state.model_dump(mode="json")
    restored = ConversationState.model_validate(snapshot)
    resolver_input = build_resolver_input("Xuat PDF", restored, {"fields": []})

    assert resolver_input.conversation_state_summary["active_report_context"]["report_id"] == "r1"


def test_complete_new_request_overrides_pending_clarification_context():
    state = ConversationState(
        active_file_id="downtime",
        pending_clarification=PendingClarification(
            active_file_id="downtime",
            original_message="Can metric nao?",
            original_intent="aggregation",
            missing_slots=["metric"],
            last_question="Ban muon dung metric nao?",
        ),
    )

    resolution = resolve_turn_relationship("Ve bieu do xu huong downtime theo ngay", state)

    assert resolution.relationship is TurnRelationship.NEW_REQUEST
