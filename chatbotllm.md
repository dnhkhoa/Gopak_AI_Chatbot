# Production LLM Chatbot Implementation and Release Audit

Audit / implementation date: 2026-06-26  
Workspace: `D:\Gopak Chatbot`  
Target product: fixed-source production analytics chatbot  
Final verdict: **NOT_READY**

This report replaces the previous audit baseline after direct inspection and implementation work across source code, configuration, ingestion/cache, routing, QueryPlan validation, SQL execution, fallback behavior, frontend, tests, benchmarks, release artifacts, and deployment documentation.

No claim below is based only on README text. PASS/FAIL/UNKNOWN states are based on files inspected and commands actually executed in this workspace.

## 1. Executive Verdict

**Final verdict: NOT_READY**

The system has been moved from a customer-facing active-file/upload flow toward the required fixed production bundle architecture:

```text
Production Analytics Bundle
+-- machine_downtime
+-- loss_assignment
`-- apqoee_cumulative
```

`Cup3.xlsx` is now configured as `apqoee_cumulative`, not as Production Raw Data. The production registry, ingestion path, customer chat path, source router, APQOEE cumulative semantics, fallback controls, and customer UI were updated accordingly.

However, the release gates do not allow `READY_FOR_CUSTOMER` because several gates are still failed or unknown:

| Gate area | Status | Reason |
|---|---|---|
| Backend tests | PASS | `python -m pytest -q`: 136 passed |
| Frontend tests | PASS | `npm test -- --run`: 20 passed |
| Frontend production build | PASS | `npm run build` passed |
| Routing benchmark | PASS | 120/120 pass in `artifacts/ROUTING_BENCHMARK_RESULTS.json` |
| Active production cache excludes old source | PASS | Active manifest/catalog contain only 3 production sources |
| Numeric oracle | PARTIAL | Only smoke oracle coverage exists; not full critical-case oracle |
| Period-specific APQOEE | LOCKED | Performance formula is not approved/configured |
| Live Ollama health | FAIL | `localhost:11434/api/tags` unreachable |
| Offline runtime | FAIL | Depends on unavailable local Ollama runtime |
| Fresh install | UNKNOWN | Not executed |
| Rollback drill | UNKNOWN | Not executed |

Because live/offline runtime, fresh install, rollback, and full numeric oracle gates are not satisfied, the maximum truthful verdict is **NOT_READY**.

## 2. Required Output Summary

The requested output artifacts were created or updated:

| Required output | Status |
|---|---|
| `docs/TARGET_ARCHITECTURE.md` | Created/updated |
| `docs/SOURCE_REGISTRY.md` | Created/updated |
| `docs/APQOEE_CUMULATIVE_SEMANTICS.md` | Created/updated |
| `docs/CUSTOMER_DEPLOYMENT_GUIDE.md` | Updated |
| `docs/CUSTOMER_ROLLBACK_GUIDE.md` | Updated |
| `docs/CUSTOMER_UAT_PLAN.md` | Updated |
| `artifacts/IMPLEMENTATION_REPORT.md` | Created |
| `artifacts/CUSTOMER_RELEASE_GATE.md` | Created |
| `artifacts/ROUTING_BENCHMARK_RESULTS.json` | Created |
| `artifacts/NUMERIC_ORACLE_RESULTS.json` | Created |
| `artifacts/FRESH_INSTALL_LOG.md` | Created, status NOT_EXECUTED |
| `artifacts/OFFLINE_RUNTIME_TEST.md` | Created, status FAIL |
| `artifacts/ROLLBACK_EXECUTION_LOG.md` | Created, status NOT_EXECUTED |

## 3. Architecture Before and After

### 3.1 Before

The previous implementation was effectively:

```text
User selects/uploads a file
-> conversation stores active_file_id
-> frontend sends source_file_id
-> backend scopes catalog/query to that file
-> planner/query path answers within one selected workbook
```

Problems observed from the baseline:

| Problem | Impact |
|---|---|
| Customer upload UI existed | Customer could introduce arbitrary workbook into chat flow |
| Frontend sent `source_file_id` | Runtime depended on active-file selection |
| Production config included old source | Old EntryTransaction architecture was still active |
| No fixed source registry | No single authoritative source identity/checksum/schema contract |
| Multi-source behavior was not target architecture | File-scoped benchmarks did not prove one/two/three-source routing |

### 3.2 After

The implemented production path is now:

```text
User Question
-> Conversation Context Resolver
-> Intent / Metric / Time Extraction
-> Source Capability Filter
-> Source Router
-> Structured QueryPlan / deterministic production service
-> Strict Plan Validation
-> Deterministic SQL/Python Execution
-> Result Validation
-> Evidence Pack
-> Grounded Answer / Table / Chart / Report
```

The customer-facing chat path uses the fixed Production Analytics Bundle:

| Source ID | Workbook | Role |
|---|---|---|
| `machine_downtime` | `Machine_Downtime_20260203_100753.xlsx` | Downtime duration/count/machine/reason analysis |
| `loss_assignment` | `Loss_Assignment_20260203_100840.xlsx` | Loss duration/count/group/reason analysis |
| `apqoee_cumulative` | `Cup3.xlsx` | APQOEE cumulative snapshots |

Customer upload is disabled by default and removed from the main customer UI. Backend upload remains gated by `CUSTOMER_UPLOAD_ENABLED`; default behavior is disabled.

## 4. Files Changed

Core production architecture and config:

| Area | Files |
|---|---|
| Source registry | `config/source_registry.json`, `src/sources/registry.py`, `src/sources/routing.py`, `src/sources/__init__.py` |
| Production service | `src/production/service.py`, `src/production/ingestion.py`, `src/production/schemas.py`, `src/production/__init__.py` |
| Global settings | `src/config.py`, `.env.example` |
| Ingestion/cache/catalog | `scripts_ingest.py`, `src/ingestion/cache_manager.py`, `src/catalog/profiler.py` |
| Chat orchestration | `src/application/chat_service.py`, `src/application/__init__.py`, `src/application/customer_intents.py` |
| Query contracts | `src/query/schemas.py`, `src/query/validator.py`, `src/query/executor.py` |
| LLM/fallback | `src/llm/planner.py`, `src/llm/prompts.py` |
| Backend API/startup | `backend/main.py`, `backend/api/routes_files.py` |
| Frontend | `frontend/src/App.tsx`, `frontend/src/api/messages.ts`, `frontend/src/mocks/fixtures.ts` |
| Tests | `tests/test_production_bundle_architecture.py`, `tests/test_web_api.py`, `tests/test_ingestion.py`, `tests/test_customer_query_understanding.py`, `tests/test_localization_capability_contract.py` |
| Docs/artifacts | Files listed in section 2 |

Note: the worktree already contained many modified and untracked artifact files before this final report. They were not reverted.

## 5. Source Registry Audit

Implemented source registry:

```json
{
  "schema_version": "2026-06-production-analytics-v1",
  "bundle_name": "Production Analytics Bundle",
  "sources": [
    "machine_downtime",
    "loss_assignment",
    "apqoee_cumulative"
  ]
}
```

Observed active source state from `config/source_registry.json` and `cache/manifest.json`:

| Source | Workbook | Table | Rows | Checksum prefix | Status |
|---|---|---|---:|---|---|
| `machine_downtime` | `Machine_Downtime_20260203_100753.xlsx` | `machine_downtime_main` | 9,151 | `5dbf77becfd1` | Active |
| `loss_assignment` | `Loss_Assignment_20260203_100840.xlsx` | `loss_assignment_main` | 36,309 | `c63cd1167af0` | Active |
| `apqoee_cumulative` | `Cup3.xlsx` | `apqoee_cumulative_main` | 944 | `d6065ade4b6c` | Active |

Registry capabilities implemented:

| Capability | Status |
|---|---|
| Stable source IDs | PASS |
| Workbook paths | PASS |
| Checksums in active manifest | PASS |
| Schema fingerprints in active manifest | PASS |
| Grain metadata | PASS |
| Timestamp semantics | PASS |
| Supported metrics | PASS |
| Business keys | PASS |
| Approved relationships field | PASS |
| Readiness/status exposed through registry/service | PASS |

## 6. Old Source Removal Audit

The production architecture was updated so the old EntryTransaction source is not part of config, source registry, production cache, catalog, customer UI, deterministic planner, prompt code, tests, fixtures, or active frontend build.

Evidence command:

```text
rg -n "EntryTransaction|entrytransaction" src backend frontend/src frontend/dist tests config scripts_ingest.py .env.example cache/manifest.json cache/data_catalog.json
```

Result:

```text
No matches
```

Historical/deprecated references may still exist in documentation or release reports only when describing the previous state.

## 7. Ingestion and Cache

Production ingestion now uses the fixed source registry and direct production-bundle path. `scripts_ingest.py` calls production ingestion when `CUSTOMER_PRODUCTION_MODE=true`.

Implemented behavior:

| Requirement | Status |
|---|---|
| Ingest exactly 3 configured production workbooks | PASS |
| Build parquet tables with source IDs | PASS |
| Record checksum/schema fingerprint | PASS |
| Rebuild data catalog | PASS |
| Prune orphaned production cache/parquet | PASS |
| Remove old source from active manifest/catalog | PASS |
| Keep upload cache out of production chat flow | PASS |

Fresh ingestion command executed:

```text
python scripts_ingest.py
```

Observed result:

```text
Loaded 3 tables. Catalog: cache/data_catalog.json
```

Active parquet files after pruning:

```text
cache/tables/apqoee_cumulative_main_d6065ade4b6c.parquet
cache/tables/loss_assignment_main_c63cd1167af0.parquet
cache/tables/machine_downtime_main_5dbf77becfd1.parquet
```

## 8. Source Routing and QueryPlan

A `SourceRoute` contract was added with constrained strategies:

```text
single_source
validated_join
parallel_queries_then_merge
clarification
not_answerable
```

Routing behavior implemented:

| Case | Expected sources | Implemented strategy |
|---|---|---|
| APQOEE-only | `apqoee_cumulative` | `single_source` |
| Downtime-only | `machine_downtime` | `single_source` |
| Loss-only | `loss_assignment` | `single_source` |
| APQOEE + Downtime | `apqoee_cumulative`, `machine_downtime` | `parallel_queries_then_merge` |
| APQOEE + Loss | `apqoee_cumulative`, `loss_assignment` | `parallel_queries_then_merge` |
| Downtime + Loss | `machine_downtime`, `loss_assignment` | `parallel_queries_then_merge` |
| All three | all production sources | `parallel_queries_then_merge` |
| Ambiguous/out-of-scope | none | `clarification` / `not_answerable` |

`QueryPlan` was extended with source-related fields:

```text
source_ids
execution_strategy
requested_grain
time_semantics
```

Validator changes:

| Validation | Status |
|---|---|
| Reject multi-table plans without joins unless strategy is `parallel_queries_then_merge` | PASS |
| Reject `parallel_queries_then_merge` as a single generated SQL query | PASS |
| Avoid table-first silent execution for unsafe multi-source plans | PASS |

## 9. APQOEE Cumulative Semantics

`Cup3.xlsx` is treated as cumulative APQOEE snapshot data.

Implemented semantics:

| Requirement | Status |
|---|---|
| `ExecuteAt` parsed as UTC-aware timestamp | PASS |
| Convert to configured business timezone before day/as-of logic | PASS |
| As-of query uses latest snapshot at or before requested time | PASS |
| End-of-day query uses latest snapshot `<=` end of business day | PASS |
| Future snapshot is not used for as-of query | PASS |
| Cumulative OEE is not treated as daily OEE | PASS |
| Trend is labeled cumulative trend | PASS |
| Period-specific OEE is rejected when Performance formula is not configured | PASS |

Locked capability:

| Capability | Status | Reason |
|---|---|---|
| Period-specific APQOEE/OEE | LOCKED | `PERFORMANCE_FORMULA_MODE` is disabled; official Performance formula is not configured |

The system may return cumulative Availability/Performance/Quality/OEE directly from snapshots. It must not calculate period-specific Performance/OEE until the business formula is approved and configured.

## 10. Downtime and Loss Time Semantics

Downtime and loss interval handling was implemented with overlap/clipping semantics.

Required interval rule:

```text
start_time < period_end
AND end_time >= period_start
```

Effective duration:

```text
effective_start = MAX(start_time, period_start)
effective_end   = MIN(end_time, period_end)
duration        = MAX(0, effective_end - effective_start)
```

Implemented coverage:

| Case | Status |
|---|---|
| Event overlaps requested day | PASS |
| Event starts before period and ends inside period | PASS |
| Event starts inside period and ends after period | PASS |
| Event spans the full period | PASS |
| Boundary `[start, end)` handling | PASS |
| Null end-time policy | Implemented defensively; still needs broader UAT data coverage |

## 11. Fallback Policy

Production fallback was tightened.

Implemented:

| Requirement | Status |
|---|---|
| Remove deterministic rescue fallback after invalid LLM retry | PASS |
| Do not silently convert invalid LLM output into success | PASS |
| Deterministic planner can be primary route before LLM | PASS |
| Production responses expose `fallback_used` | PASS |
| Production responses expose `execution_mode` | PASS |

Observed production metadata:

```text
fallback_used=false
execution_mode=DETERMINISTIC_PRODUCTION
```

Remaining limitation: live structured-output LLM smoke could not be executed because the local Ollama runtime was unavailable.

## 12. Backend and Runtime

Backend changes:

| Requirement | Status |
|---|---|
| Customer upload disabled by default | PASS |
| Upload route returns forbidden when disabled | PASS |
| Production chat ignores frontend `source_file_id` | PASS |
| Production health includes source/model degradation signals | PASS |
| Startup skips upload reconciliation when production upload is disabled | PASS |
| Query execution applies memory/row/resource-oriented limits where available | PARTIAL |

Startup smoke was executed after fixes:

| Component | Result |
|---|---|
| Backend `/api/health` | PASS, returned `ok` |
| Frontend HTTP smoke | PASS, HTTP 200 |
| Ollama health | FAIL, unable to connect |

No leftover `python` or `node` process was observed after the final checks.

## 13. Frontend

Customer UI changes:

| Requirement | Status |
|---|---|
| Remove upload dropzone from customer flow | PASS |
| Remove uploaded files panel from customer flow | PASS |
| Remove file selector / active-file customer workflow | PASS |
| Stop sending `source_file_id` from frontend chat request | PASS |
| Show fixed Production Analytics Bundle context | PASS |
| Preserve New Chat / History flow | PASS |

Frontend test/build verification:

```text
npm test -- --run
```

Result:

```text
5 test files passed
20 tests passed
```

```text
npm run build
```

Result:

```text
Build passed
Warning: one JS chunk is larger than 500 kB after minification
```

## 14. Tests and Benchmarks

### 14.1 Backend Test Run

Command:

```text
python -m pytest -q
```

Result:

```text
136 passed, 19 warnings in 180.88s (0:03:00)
```

Warnings were FastAPI/Starlette deprecation warnings around `on_event` / TestClient compatibility, not test failures.

### 14.2 Frontend Test Run

Command:

```text
npm test -- --run
```

Result:

```text
5 test files passed
20 tests passed
```

### 14.3 Frontend Production Build

Command:

```text
npm run build
```

Result:

```text
PASS
```

Vite emitted a chunk-size warning for `assets/index-*.js` (~595 kB minified). This is not a build failure but should be optimized before a polished customer package.

### 14.4 Routing Benchmark

Artifact:

```text
artifacts/ROUTING_BENCHMARK_RESULTS.json
```

Summary:

| Metric | Result |
|---|---:|
| Total cases | 120 |
| Passed | 120 |
| Failed | 0 |
| Single-source cases | 50 |
| Two-source cases | 30 |
| Three-source cases | 20 |
| Clarification/out-of-scope cases | 20 |
| Single-source accuracy | 100% |
| Two-source accuracy | 100% |
| Three-source accuracy | 100% |
| Clarification accuracy | 100% |
| Unsafe source inclusion | 0 |
| Silent fallback | 0 |

Limitation: this benchmark verifies the deterministic source router over generated/paraphrased cases. It does not replace live customer UAT or full numeric oracle verification.

### 14.5 Numeric Oracle

Artifact:

```text
artifacts/NUMERIC_ORACLE_RESULTS.json
```

Summary:

| Metric | Result |
|---|---:|
| Total oracle smoke cases | 4 |
| Passed | 4 |
| Failed | 0 |

Covered smoke cases:

| Case | Status |
|---|---|
| Cumulative OEE as-of 2025-11-10 | PASS |
| Downtime on 2025-11-10 | PASS |
| Loss on 2025-11-10 | PASS |
| Three-source summary through 2025-11-10 | PASS |

Limitation: this is partial smoke coverage. It does not satisfy the requested 100% critical numeric oracle gate for all period, boundary, cross-midnight, loss-range, and multi-source comparison cases.

## 15. Release Verification

| Required verification | Result | Evidence |
|---|---|---|
| Full backend tests | PASS | `python -m pytest -q` |
| Full frontend tests | PASS | `npm test -- --run` |
| Frontend production build | PASS | `npm run build` |
| Backend startup | PASS | `/api/health` returned `ok` |
| Frontend startup | PASS | HTTP 200 |
| Live Ollama health | FAIL | `localhost:11434/api/tags` unreachable |
| Live structured-output smoke | NOT_EXECUTED | Blocked by Ollama health failure |
| Offline runtime test | FAIL | `artifacts/OFFLINE_RUNTIME_TEST.md` |
| Fresh ingestion from 3 workbooks | PASS | `python scripts_ingest.py` loaded 3 tables |
| Clean cache rebuild | PASS | Active cache contains only 3 production parquet files |
| Customer UAT | UNKNOWN | Full customer UAT not executed |
| Fresh install | UNKNOWN | `artifacts/FRESH_INSTALL_LOG.md` says NOT_EXECUTED |
| Rollback drill | UNKNOWN | `artifacts/ROLLBACK_EXECUTION_LOG.md` says NOT_EXECUTED |

## 16. Release Gates

| Gate | Required | Actual | Decision |
|---|---|---|---|
| Backend tests | 100% pass | 136 passed | PASS |
| Frontend tests | 100% pass | 20 passed | PASS |
| Frontend production build | pass | pass | PASS |
| Single-source routing | >= 98% | 100% | PASS |
| Two-source routing | >= 95% | 100% | PASS |
| Three-source routing | >= 95% | 100% | PASS |
| Numeric oracle critical cases | 100% | partial smoke only | FAIL |
| Cumulative/period temporal semantics | 100% | cumulative ready, period APQOEE locked | FAIL |
| Unsafe multi-table execution | 0 | 0 in tests/benchmark | PASS |
| Silent fallback | 0 | 0 in production benchmark | PASS |
| Stale source/cache usage | 0 | 0 in active manifest/catalog scan | PASS |
| Critical UAT failures | 0 | UAT not executed | UNKNOWN |
| Live Ollama smoke test | pass | failed | FAIL |
| Offline runtime test | pass | failed | FAIL |
| Fresh install | pass | not executed | UNKNOWN |
| Rollback drill | pass | not executed | UNKNOWN |

Release gate result:

```text
NOT_READY
```

## 17. Closed Blockers

| ID | Baseline blocker | Current status |
|---|---|---|
| B-001 | Customer architecture was active-file/upload scoped | Closed for production customer path |
| B-002 | Old EntryTransaction source was configured | Closed for active production source/config/cache/test/UI path |
| B-003 | No fixed source registry | Closed |
| B-004 | No explicit source router contract | Closed |
| B-005 | Frontend sent `source_file_id` | Closed |
| B-006 | Upload API participated in customer product by default | Closed; disabled by default |
| B-007 | Multi-table plan could silently ignore extra tables | Closed by validator strategy checks |
| B-008 | LLM failure could be silently rescued by deterministic fallback | Closed in production path |
| B-009 | Static cache could retain stale configured sources | Closed for production rebuild/prune path |
| B-010 | APQOEE cumulative semantics were not represented | Closed for cumulative/as-of/trend path |

## 18. Remaining Issues

| ID | Severity | Issue | Required action |
|---|---|---|---|
| R-001 | BLOCKER | Local Ollama runtime unavailable | Install/start Ollama and required model; rerun live health and structured-output smoke |
| R-002 | BLOCKER | Offline runtime test fails | Rerun after local model is installed and reachable offline |
| R-003 | BLOCKER | Fresh install not executed | Run clean-machine or clean-environment install and capture logs |
| R-004 | BLOCKER | Rollback drill not executed | Execute rollback procedure and capture result |
| R-005 | BLOCKER | Numeric oracle is partial | Add independent expected values for all critical APQOEE/downtime/loss/multi-source cases |
| R-006 | BLOCKER | Period-specific APQOEE/OEE locked | Configure approved Performance formula or keep capability disabled |
| R-007 | HIGH | Full customer UAT not executed | Run UAT plan against customer-style workflows |
| R-008 | MEDIUM | Frontend bundle chunk warning | Consider code splitting/manual chunks before release packaging |
| R-009 | MEDIUM | FastAPI deprecation warnings | Migrate startup events to lifespan handlers |

## 19. Capability Matrix

| Capability | Status | Notes |
|---|---|---|
| Cumulative APQOEE as-of | READY_WITHIN_CURRENT_TEST_SCOPE | Requires `BUSINESS_TIMEZONE` configuration |
| Cumulative APQOEE trend | READY_WITHIN_CURRENT_TEST_SCOPE | Labeled as cumulative trend |
| Period-specific APQOEE/OEE | LOCKED | Requires approved Performance formula |
| Machine downtime daily/range | READY_WITHIN_CURRENT_TEST_SCOPE | Uses interval overlap/clipping |
| Loss daily/range | READY_WITHIN_CURRENT_TEST_SCOPE | Uses production loss source |
| Single-source routing | READY_WITHIN_BENCHMARK_SCOPE | 50/50 benchmark pass |
| Two-source routing | READY_WITHIN_BENCHMARK_SCOPE | 30/30 benchmark pass |
| Three-source routing | READY_WITHIN_BENCHMARK_SCOPE | 20/20 benchmark pass |
| Customer upload | DISABLED_BY_DEFAULT | Removed from customer UI |
| Live LLM path | NOT_READY | Ollama unavailable |
| Offline deployment | NOT_READY | Depends on unavailable Ollama |
| Fresh deploy package | NOT_READY | Fresh install not executed |
| Rollback recovery | NOT_READY | Drill not executed |

## 20. Evidence Appendix

### 20.1 Source and Config Evidence

| Evidence | Meaning |
|---|---|
| `config/source_registry.json` | Fixed 3-source registry |
| `src/config.py` | Production mode, upload disabled by default, registry-derived target files |
| `src/sources/registry.py` | Registry loading/checksum/schema/readiness |
| `src/sources/routing.py` | SourceRoute and source routing |
| `src/production/ingestion.py` | Production bundle ingestion and cache pruning |
| `src/production/service.py` | Deterministic production analytics path |
| `src/application/chat_service.py` | Production chat path and public metadata |
| `backend/api/routes_files.py` | Upload disabled by default |
| `frontend/src/App.tsx` | Customer UI without upload/file selector |

### 20.2 Test and Verification Evidence

| Evidence | Result |
|---|---|
| `python -m pytest -q` | 136 passed, 19 warnings |
| `npm test -- --run` | 20 tests passed |
| `npm run build` | Passed with chunk warning |
| `python scripts_ingest.py` | Loaded 3 production tables |
| Backend startup smoke | `/api/health` returned `ok` |
| Frontend startup smoke | HTTP 200 |
| Ollama health check | Failed to connect |

### 20.3 Artifact Evidence

| Artifact | Status |
|---|---|
| `artifacts/IMPLEMENTATION_REPORT.md` | Summarizes implementation |
| `artifacts/CUSTOMER_RELEASE_GATE.md` | Release gate verdict NOT_READY |
| `artifacts/ROUTING_BENCHMARK_RESULTS.json` | 120/120 routing pass |
| `artifacts/NUMERIC_ORACLE_RESULTS.json` | 4/4 smoke oracle pass, partial |
| `artifacts/OFFLINE_RUNTIME_TEST.md` | FAIL |
| `artifacts/FRESH_INSTALL_LOG.md` | NOT_EXECUTED |
| `artifacts/ROLLBACK_EXECUTION_LOG.md` | NOT_EXECUTED |

## 21. Final Go / No-Go

| Release type | Decision |
|---|---|
| Production customer release | **NO-GO** |
| Customer pilot for real operational decisions | **NO-GO** |
| Internal demo of fixed-source production path | Conditional GO |
| Continued development toward customer release | GO |

## 22. Final Verdict

```text
NOT_READY
```

Reason: release gates for live Ollama, offline runtime, fresh install, rollback drill, full numeric oracle, and period-specific APQOEE readiness are not satisfied.
