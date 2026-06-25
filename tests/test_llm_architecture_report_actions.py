from evaluation.llm_architecture_benchmark import report_action
from src.llm.semantic_contracts import SemanticIntent, SemanticResolution, TurnRelationship
from src.llm.semantic_resolver import build_resolver_input, validate_semantic_resolution
from src.conversation.artifacts import ActiveReportContext
from src.conversation.state import ConversationState


def test_report_action_helper_accepts_relationship_enum():
    assert report_action("Xuat PDF bao cao nay", TurnRelationship.ARTIFACT_EXPORT) == "export"
    assert report_action("Chi tiet hon", TurnRelationship.ARTIFACT_REVISION) == "revise"


def test_report_export_is_not_routed_to_analytics_or_clarification():
    state = ConversationState(
        active_file_id="downtime",
        active_report_context=ActiveReportContext(report_id="r1", root_report_id="r1", source_file_id="downtime"),
    )
    resolver_input = build_resolver_input("Xuat PDF bao cao nay", state, {"fields": []})
    resolution = SemanticResolution(
        intent=SemanticIntent.REPORT_EXPORT,
        turn_relationship=TurnRelationship.ARTIFACT_EXPORT,
        requested_outputs=["report"],
        requested_report_action="export",
        clarification_required=False,
    )

    validation = validate_semantic_resolution(resolution, resolver_input)

    assert validation.passed is True
    assert resolution.intent is not SemanticIntent.AGGREGATION
