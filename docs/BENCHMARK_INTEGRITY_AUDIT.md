# Benchmark Integrity Audit

Date: 2026-06-23

## Scope

Audited `evaluation/conversation_architecture_cases.json` for exact duplicates, normalized duplicates, dev/holdout near-duplicates, source phrase leakage, and oracle independence.

## Results

- Cases: 360
- Utterances: 648
- Exact duplicate groups: 15
- Normalized duplicate groups: 27
- Dev/holdout near-duplicate pairs: 4126
- Source phrase leakage in `src/` or `backend/`: 0

Detailed artifact: `artifacts/conversation_benchmark_integrity.json`.

## Conclusion

The conversation benchmark is useful as a regression suite, but the holdout split is not independent enough to support customer-readiness alone. The source leakage issue found around chart-overview slot clarification was removed by replacing exact utterance matching with generic slot detection.

Because dev/holdout near-duplicate overlap remains high, customer readiness must rely on additional challenge and black-box UAT benchmarks rather than the 360/360 result alone.

## Oracle Independence

Conversation expected fields are static JSON expectations consumed by the runner. The runner checks response type, SQL execution, pending state, and REAL_LLM metadata. It does not compute numeric answers using production query functions, so numeric oracle leakage is limited; however, this benchmark is not a full numeric-grounding benchmark.
