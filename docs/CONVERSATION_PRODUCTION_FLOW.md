# Conversation Production Flow

Updated: 2026-06-22

Target production path:

```text
User message
-> load selected-file context
-> resolve pending clarification
-> resolve topic continuation/switch
-> deterministic or REAL_LLM semantic understanding
-> complete structured request
-> validated QueryPlan
-> safe SQL
-> DuckDB
-> grounded answer
-> persist conversation state
```

Rules:

- Pending clarification is checked before normal routing.
- Short answers are never treated as standalone analytical queries while pending state exists.
- File context is saved before switching files and restored after returning.
- QueryPlan validation remains mandatory.
- LLM never writes SQL.
- Clarification/refusal/safe failure never executes SQL.
- Legacy fallback remains disabled.
