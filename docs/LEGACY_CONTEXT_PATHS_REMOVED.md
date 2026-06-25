# Legacy Context Paths Removed

This refactor removes or deprecates the highest-risk context shortcuts that caused stale result and report routing regressions.

## Removed From Customer Report Path

- HTML report download button.
- Excel report download button.
- Generic `DownloadActions` and `SourceDetails` under `response_type="report"`.
- Report rendering through generic chart/table fallback.

## Deprecated In Routing

- Pending clarification can no longer automatically consume every short follow-up. It is only consumed when the turn resolver classifies the message as `CLARIFICATION_ANSWER`.
- Report follow-ups no longer enter the analytics planner first. `ARTIFACT_REVISION` and `ARTIFACT_EXPORT` resolve against `active_report_context`.
- New self-contained requests clear stale pending clarification before planning.

## Replaced With Typed Paths

- `last_visible_artifact_id` and `last_visible_artifact_type` replace implicit references to whichever result happened to be cached last.
- `ActiveReportContext` replaces ad hoc report state.
- `ConversationArtifact` snapshots replace untyped "last report" assumptions.
- `TurnResolution` metadata replaces route decisions hidden inside individual services.
- `ArtifactConsistencyValidator` replaces unvalidated stitching of narrative/table/chart artifacts.

## Still Present For Compatibility

The following fields remain because older planner and tests still depend on them:

- `last_result_summary`
- `last_result_cache_id`
- `last_plan`
- `active_*` planner fields
- `topic_frames`

They should be treated as compatibility state. New multi-turn behavior should prefer typed artifact references and explicit `TurnResolution`.
