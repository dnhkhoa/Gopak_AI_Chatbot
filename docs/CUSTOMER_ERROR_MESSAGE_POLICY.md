# Customer Error Message Policy

Customer-visible errors should be written as product messages, not backend traces.

Examples:

- No selected file: "Please select a Ready Excel file before asking data questions."
- Source unavailable: "The source file for this conversation is no longer available. Select another file to start a new chat."
- File not queryable: "The selected Excel file is not queryable. Please re-upload it or start a new chat with another Ready file."
- Safe query failure: "Please ask a more specific question within the selected Excel file."

Forbidden in customer text:

- `SAFE_FAILURE`
- `REAL_LLM`
- `DETERMINISTIC`
- `fallback`
- `QueryPlan`
- model names
- raw SQL
- tracebacks
