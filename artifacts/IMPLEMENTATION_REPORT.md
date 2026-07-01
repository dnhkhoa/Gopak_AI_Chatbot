# Implementation Report

## Changed Files

- `config/source_registry.json`
- `src/config.py`
- `src/sources/*`
- `src/production/*`
- `src/ingestion/cache_manager.py`
- `src/catalog/profiler.py`
- `scripts_ingest.py`
- `src/application/chat_service.py`
- `src/application/__init__.py`
- `src/query/schemas.py`
- `src/query/validator.py`
- `src/query/executor.py`
- `src/llm/planner.py`
- `src/routing/router.py`
- `backend/main.py`
- `backend/api/routes_files.py`
- `frontend/src/App.tsx`
- `frontend/src/api/messages.ts`
- `.env.example`
- production tests and release docs/artifacts

## Architecture Before

One conversation was bound to one uploaded or selected active file. EntryTransaction was configured. Upload UI and upload API were part of the customer flow.

## Architecture After

Customer chat uses a fixed Production Analytics Bundle with `machine_downtime`, `loss_assignment`, and `apqoee_cumulative`. Source routing happens before execution. Upload is disabled by default and removed from customer UI.

## Closed Blockers

- EntryTransaction removed from production registry and active cache/catalog.
- Customer upload UI removed.
- `source_file_id` no longer sent by frontend.
- Production source router added.
- Multi-table SQL without joins is rejected.
- LLM deterministic fallback after invalid output is removed.
- Public metadata includes status, sources, time scope, metric scope, data version, execution mode, and fallback flag.
- Static production cache rebuild prunes orphaned parquet/cache.

## Tests Run

- `python -m pytest -q`: 136 passed, 19 warnings.
- `npm test -- --run`: 20 passed.
- `npm run build`: pass, with Vite chunk size warning.
- `python scripts_ingest.py`: loaded 3 production tables.
- Backend startup smoke: `/api/health` returned `ok`.
- Frontend startup smoke: HTTP 200.
- Ollama health: failed, unable to connect to `localhost:11434`.

## Remaining Issues

- Live Ollama smoke failed.
- Offline runtime test failed by dependency: local Ollama not reachable.
- Fresh-machine install was not executed.
- Rollback drill was not executed.
- Period-specific APQOEE Performance/OEE remains locked until `PERFORMANCE_FORMULA_MODE` is configured with approved business formula.

## Release Verdict

NOT_READY
