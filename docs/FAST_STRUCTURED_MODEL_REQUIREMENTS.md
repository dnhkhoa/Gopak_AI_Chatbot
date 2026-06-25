# Fast Structured Model Requirements

The dual-model architecture must not be enabled until a local text-only fast structured model is installed and passes this gate.

## Candidate Constraints

- Must be available locally through Ollama before benchmark execution.
- Must be text-first, not a vision-language model.
- Must support JSON schema or reliably follow structured output.
- Must show meaningful latency or memory benefit over the composer model.
- Must understand Vietnamese requests with accents, without accents, and common typos.

`qwen3-vl:8b` is not accepted as the fast structured model because it is multimodal, close in size to `qwen3.5:9b`, and does not provide a clear router-specific resource advantage.

## Acceptance Gate

- JSON schema validity >= 98%.
- Strict enum validity >= 95%.
- Turn relationship accuracy >= current baseline.
- Typo recovery meets or exceeds current baseline.
- Unnecessary clarification rate does not increase.
- Wrong artifact reference count is zero in the critical suite.
- Warm p50 latency is materially lower than the composer model.
- Context replay pass rate does not regress.
- Numeric grounding is not worse than baseline.

## Suggested Future Candidates

Do not install automatically. After explicit approval, evaluate text models such as:

- `qwen2.5:3b-instruct`
- `llama3.2:3b`
- another local small text model with strong JSON compliance and Vietnamese understanding

## Out of Scope

Embedding models are not part of A/B/C architecture benchmarking. They may be evaluated separately for data dictionary retrieval, column alias retrieval, long-term preferences, semantic memory, or similar incident retrieval.
