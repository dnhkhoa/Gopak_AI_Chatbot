# Topic Memory Design

## Stored State

Each active file keeps its own conversation context:

- active table, metrics, dimensions, filters, ranking, output
- last query plan and last result summary
- topic frames
- pending clarification

This state is saved on file switch and restored when the file is selected again.

## Topic Restoration

`restore_topic_plan()` handles phrases such as `quay lai`, `luc nay`, `truoc do`, `nhu tren`, and `ban dau`. It restores the latest compatible topic frame for the active file, validates that the plan table is still in the scoped catalog, then applies small deltas such as `them so lan dung` or `ve bieu do`.

## Clarification Behavior

The clarification resolver now refuses to start a pending slot flow when the user already supplied a complete top/chart request. This prevents loops such as repeatedly asking for top count or dimension after `top 5 may theo downtime`.

## File A -> B -> A

Topic frames are saved per file through `ConversationState.save_file_context()` and restored through `restore_file_context()`. Cross-file benchmark sequences pass 40/40 after this round.
