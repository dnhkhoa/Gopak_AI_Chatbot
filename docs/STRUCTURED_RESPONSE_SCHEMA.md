# Structured Response Schema

The persisted snapshot is the existing production `ChatResponse` JSON payload:

- `message_id`
- `conversation_id`
- `response_type`
- `title`, `summary`, `primary_value`, `secondary_value`
- `table`
- `chart`
- `dashboard`
- `sources`
- `filters`
- `downloads`
- `metadata`

The payload is JSON-safe and stores only the presentation data returned to the user, not DataFrame objects, full datasets, raw prompts, chain of thought, credentials, or absolute source paths.

For legacy assistant turns without `response_json`, history returns the text content and the frontend renders it as a plain assistant message.
