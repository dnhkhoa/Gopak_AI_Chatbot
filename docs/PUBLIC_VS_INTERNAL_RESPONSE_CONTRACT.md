# Public Vs Internal Response Contract

## Public Customer Response

Customer-facing responses include:

- answer title/summary/value;
- table/chart/dashboard payloads;
- sources;
- filters;
- downloads;
- minimal provenance metadata: source file ID/name and file-scope validation.

They do not include execution mode, model name, LLM latency, route reason, fallback status, raw SQL, prompts, or chain of thought.

## Internal Diagnostics

Internal diagnostics are available only when `SHOW_INTERNAL_DEBUG_METADATA=true`. In that mode the API can return `internal_debug_metadata` for local QA and seed/evaluation scripts.

Default customer builds keep this flag off.
