# Conversation Benchmark Design

Updated: 2026-06-22

The benchmark uses the production `ChatApplicationService` path with real active-file selection. It does not call parser-only functions as the final oracle.

Case groups:

- Simple deterministic.
- Semantic natural language.
- Clarification resolution.
- Topic A -> B -> A.
- File A -> B -> A.
- Multi-part questions.
- Row-level/time interval.
- Topic switch during clarification.
- Restart persistence.
- Safety/refusal.

Scoring uses deterministic assertions for:

- response type;
- execution mode;
- active file id;
- SQL/no-SQL;
- repeated clarification loops;
- LLM invocation;
- topic/file restoration;
- numeric grounding where available.

LLM judge is not used for numeric correctness.
