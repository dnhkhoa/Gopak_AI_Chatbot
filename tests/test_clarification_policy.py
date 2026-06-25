from src.conversation.artifacts import ActiveReportContext
from src.conversation.state import ConversationState, PendingClarification
from src.conversation.turn_resolution import resolve_turn_relationship
from src.llm.semantic_contracts import SemanticIntent, SemanticResolution, TurnRelationship
from src.llm.semantic_resolver import build_resolver_input, validate_semantic_resolution


def test_report_export_does_not_request_metric_clarification_when_context_exists():
    state = ConversationState(
        active_file_id="downtime",
        active_report_context=ActiveReportContext(report_id="r1", root_report_id="r1", source_file_id="downtime"),
    )
    resolver_input = build_resolver_input("Xuat PDF", state, {"fields": []})
    resolution = SemanticResolution(
        intent=SemanticIntent.REPORT_EXPORT,
        turn_relationship=TurnRelationship.ARTIFACT_EXPORT,
        referenced_artifact_type="REPORT",
        requested_outputs=["report"],
        requested_report_action="export",
        clarification_required=False,
    )

    validation = validate_semantic_resolution(resolution, resolver_input)

    assert validation.passed is True


def test_report_revision_clarification_is_rejected():
    state = ConversationState(active_file_id="downtime")
    resolver_input = build_resolver_input("Chi tiet hon", state, {"fields": []})
    resolution = SemanticResolution(
        intent=SemanticIntent.REPORT_REVISION,
        turn_relationship=TurnRelationship.ARTIFACT_REVISION,
        requested_outputs=["report"],
        requested_report_action="revise",
        clarification_required=True,
        clarification_slots=["metric"],
    )

    validation = validate_semantic_resolution(resolution, resolver_input)

    assert validation.passed is False
    assert "UNNECESSARY_CLARIFICATION" in validation.failure_classification


def test_pending_clarification_does_not_consume_complete_new_request():
    state = ConversationState(
        active_file_id="downtime",
        pending_clarification=PendingClarification(
            active_file_id="downtime",
            original_message="May nao?",
            original_intent="ranking",
            missing_slots=["metric"],
            last_question="Ban muon dung metric nao?",
        ),
    )

    resolution = resolve_turn_relationship("Top 5 may downtime cao nhat", state)

    assert resolution.relationship is TurnRelationship.NEW_REQUEST
