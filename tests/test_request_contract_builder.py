from src.conversation.artifacts import ActiveReportContext
from src.conversation.state import ConversationState
from src.llm.request_contract_builder import RequestContractBuilder
from src.llm.semantic_contracts import SemanticIntent, SemanticResolution, TurnRelationship


def test_new_request_resets_stale_context_deterministically():
    state = ConversationState(active_file_id="downtime", active_dimensions=["old_dimension"])
    resolution = SemanticResolution(
        intent=SemanticIntent.AGGREGATION,
        turn_relationship=TurnRelationship.NEW_REQUEST,
        metrics=["total_downtime"],
    )

    result = RequestContractBuilder().build(resolution, state, {"fields": ["total_downtime"], "capabilities": ["downtime"]})

    assert result.valid is True
    assert result.contract is not None
    assert result.contract.relation_to_previous_turn == "NEW_REQUEST"
    assert "pending_clarification" in result.contract.explicitly_reset_fields
    assert result.contract.inherited_fields == []


def test_builder_rejects_wrong_file_capability_request():
    state = ConversationState(active_file_id="transactions")
    resolution = SemanticResolution(
        intent=SemanticIntent.AGGREGATION,
        turn_relationship=TurnRelationship.NEW_REQUEST,
        metrics=["total_downtime"],
    )

    result = RequestContractBuilder().build(
        resolution,
        state,
        {"fields": ["transaction_value"], "capabilities": ["transaction_value"]},
    )

    assert result.valid is False
    assert "FIELD_MAPPING_WRONG" in result.failure_classification


def test_report_export_requires_active_report_context():
    resolution = SemanticResolution(
        intent=SemanticIntent.REPORT_EXPORT,
        turn_relationship=TurnRelationship.ARTIFACT_EXPORT,
        requested_outputs=["report"],
        requested_report_action="export",
    )
    state = ConversationState(active_file_id="downtime")

    result = RequestContractBuilder().build(resolution, state, {"fields": [], "capabilities": ["report"]})

    assert result.valid is False
    assert "ARTIFACT_REFERENCE_WRONG" in result.failure_classification


def test_report_export_contract_inherits_report_context_when_present():
    state = ConversationState(
        active_file_id="downtime",
        active_report_context=ActiveReportContext(report_id="r1", root_report_id="r1", source_file_id="downtime"),
    )
    resolution = SemanticResolution(
        intent=SemanticIntent.REPORT_EXPORT,
        turn_relationship=TurnRelationship.ARTIFACT_EXPORT,
        requested_outputs=["report"],
        requested_report_action="export",
    )

    result = RequestContractBuilder().build(resolution, state, {"fields": [], "capabilities": ["report"]})

    assert result.valid is True
    assert result.contract is not None
    assert result.contract.intent == "report"
    assert "active_report_context" in result.contract.inherited_fields
