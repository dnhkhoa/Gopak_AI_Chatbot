# Conversation State Model

Updated: 2026-06-22

Production state remains Pydantic and SQLite-backed.

## PendingClarification

Stores the active slot-filling task before normal routing.

Fields:

- `clarification_id`
- `active_file_id`
- `original_message`
- `original_intent`
- `partial_request`
- `missing_slots`
- `resolved_slots`
- `allowed_metrics`
- `allowed_dimensions`
- `allowed_outputs`
- `allowed_values`
- `last_question`
- `attempts`

## TopicFrame

Stores one resumable analytical topic per file.

Fields:

- `topic_id`
- `active_file_id`
- `label`
- `intent`
- `metrics`
- `dimensions`
- `filters`
- `time_range`
- `ranking`
- `output_type`
- `last_query_plan`
- `last_result_summary`

## FileConversationContext

Scopes context by selected file:

- `file_id`
- `active_topic_id`
- `topic_frames`
- `pending_clarification`

## ConversationState

Top-level state keeps:

- `active_file_id`
- `active_file_name`
- `file_contexts`
- current analytical fields for compatibility
- `pending_clarification`
- `current_message`
- `resolved_request`
- `last_execution_mode`

Frameworks do not define business state. They may only orchestrate transitions over this model.
