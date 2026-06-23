# Answer Quality And Customer UI Audit

## Current Flow

User messages go through file-scope checks, optional clarification handling, row-level handlers, metadata intent handlers, then `QueryPlanner -> SafeQueryExecutor -> PresentedResponse -> ChatResponse`.

## Root Causes Found

- Many deterministic answers used `PresentedResponse.summary` directly, which made top-N and chart answers too terse.
- Semantic follow-up questions such as "Kết quả này nói lên điều gì?" could be routed back to a structured query instead of a narrative explanation.
- Technical metadata lived inside `ChatResponse.metadata` and could be rendered by developer components when enabled.

## Changes

- Added a grounded semantic follow-up path that calls Ollama only for interpretation/commentary over the last validated result.
- Added richer deterministic summaries after query execution without inventing new numbers.
- Added public response sanitization: customer responses keep business provenance only and omit execution mode, model name, latency, router reason, and fallback data unless internal diagnostics are explicitly enabled.

## Risks

- The codebase still has older duplicate methods in `chat_service.py`; the active methods are the later definitions. A future cleanup should remove the stale block to reduce maintenance risk.
- Full `PublicChatResponse` / `InternalChatTrace` split is documented but not yet a physically separate database table.
