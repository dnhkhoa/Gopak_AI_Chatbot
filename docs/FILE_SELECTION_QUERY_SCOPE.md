# File Selection Query Scope

Updated: 2026-06-22

## Active File Rule

Every data question requires one active file.

`PUT /api/conversations/{conversation_id}/active-file` now validates:

- file exists in uploaded metadata;
- file status is `ready`;
- `queryable=true`;
- readiness checks pass against current catalog/cache.

If validation fails, the API returns conflict/error instead of binding the conversation to a broken file.

## Query Rule

Before SQL planning/execution, chat preflight checks the active file again.

If no active file exists, the assistant asks the user to select one.

If the active file is processing, failed, deleted, or not queryable, the assistant returns a safe failure and does not run SQL.

If the user mentions another uploaded file while a different file is active, the assistant refuses and asks the user to switch files first.

## Catalog Scope

`ChatApplicationService.get_catalog_for_file(file_id)` filters catalog tables by `file_id/source_file_id`. Filename matching is only a legacy fallback when an older catalog has no file id metadata.

The query planner and SQL executor receive only the scoped catalog for the active file.
