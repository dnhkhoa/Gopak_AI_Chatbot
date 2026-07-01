# Customer Release Gate

Verdict: **NOT_READY**

| Gate | Result | Evidence |
|---|---|---|
| Backend tests 100% pass | PASS | `python -m pytest -q`: 136 passed |
| Frontend tests 100% pass | PASS | `npm test -- --run`: 20 passed |
| Frontend production build | PASS | `npm run build` passed |
| Single-source routing >= 98% | PASS | `artifacts/ROUTING_BENCHMARK_RESULTS.json` |
| Two-source routing >= 95% | PASS | `artifacts/ROUTING_BENCHMARK_RESULTS.json` |
| Three-source routing >= 95% | PASS | `artifacts/ROUTING_BENCHMARK_RESULTS.json` |
| Numeric oracle critical cases 100% | PARTIAL | `artifacts/NUMERIC_ORACLE_RESULTS.json` has only smoke oracle coverage |
| Cumulative/period temporal semantics | PARTIAL | Cumulative implemented; period APQOEE locked |
| Unsafe multi-table execution = 0 | PASS | Validator rejects multi-table no-join plans |
| Silent fallback = 0 | PASS | Production responses set `fallback_used=false`; LLM rescue fallback removed |
| Stale source/cache usage = 0 | PASS | Active cache/catalog has 3 production sources and no EntryTransaction |
| Critical UAT failures = 0 | UNKNOWN | Full customer UAT not executed |
| Live Ollama smoke test | FAIL | `localhost:11434/api/tags` unreachable |
| Offline runtime test | FAIL | Requires local Ollama availability |
| Fresh install | UNKNOWN | Not executed |
| Rollback drill | UNKNOWN | Not executed |

Maximum allowed verdict while Performance formula is disabled and live/offline/fresh/rollback gates are not met: **NOT_READY**.
