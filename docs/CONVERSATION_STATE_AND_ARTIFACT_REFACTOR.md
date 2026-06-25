# Conversation State And Artifact Refactor

## Root Cause

The repeated regressions came from split context ownership. Planner state, pending clarification, last result cache, report payloads, and frontend rendering decisions were each using separate shortcuts. A new turn could therefore inherit an old plan or result without an explicit artifact reference.

## State Model

`ConversationState` is now the single persisted owner of:

- active file identity
- pending clarification
- last visible artifact id/type
- active report context
- bounded immutable artifact history
- state version and update timestamp

Legacy fields such as `last_result_summary` and `last_plan` still exist for compatibility, but new routing decisions should use typed artifact context first.

## Turn Relationship

Every message is resolved by `resolve_turn_relationship()` before planner execution. The resolver emits:

- `NEW_REQUEST`
- `FOLLOW_UP_QUESTION`
- `ARTIFACT_REVISION`
- `ARTIFACT_EXPORT`
- `CLARIFICATION_ANSWER`
- `CORRECTION`
- `CANCEL`
- `AMBIGUOUS`

Report revision/export is handled before generic clarification and before SQL planning. This prevents report follow-ups such as "Chi tiết hơn" and "Xuất PDF" from being misrouted to metric/dimension clarification.

## Artifact Model

Each visible response is registered as a `ConversationArtifact` with:

- artifact id/type
- conversation id and turn id
- source file id
- parent/root artifact ids
- revision number
- request/query lineage ids
- payload snapshot

Reports additionally update `ActiveReportContext`, including the current report snapshot and PDF artifact id. History reload uses the saved response payload and state snapshot; it does not rerun SQL, LLM, or PDF generation.

## Report Workflow

The report workflow is now:

1. Generate `ReportPayload`.
2. Render `ReportPreview` from that payload.
3. Render offline PDF from the same payload.
4. Register the report artifact in state.
5. Persist message, response, artifact context, and state.

Report revisions clone the previous payload snapshot, set a new `report_id`, preserve `root_report_id`, set `parent_report_id`, increment `revision_number`, and render a fresh PDF. Export reuses the current report PDF when it still exists.

## Consistency Validation

`ArtifactConsistencyValidator` runs before persistence and checks:

- source presence
- scope coherence
- filters shape
- chart dimensions and metrics
- absence of `NaN`
- lineage presence for analytical artifacts

The validation result is stored internally in response metadata and stripped from public responses unless debug metadata is enabled.

## Public Contract

Frontend dispatch remains based on `response_type`. Report responses use `ReportPreview` and do not render generic download/source components. Customer report UI exposes only the PDF button.

## Known Limits

The artifact history is stored in `conversation_states.state_json`, not yet in a separate normalized `artifacts` table. This is enough for current replay/history behavior, but a future production migration should move artifact records to a dedicated table for indexing and retention controls.
