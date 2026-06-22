# Web Migration Report

Updated: 2026-06-21

## Summary

The project now has a React + FastAPI web path while keeping Streamlit as a legacy fallback.

The query pipeline, ingestion, DuckDB execution, planner, memory, and evaluation artifacts were not rewritten. They are reused through `ChatApplicationService`.

## Files Created

Backend:

- `backend/main.py`
- `backend/dependencies.py`
- `backend/api/routes_health.py`
- `backend/api/routes_conversations.py`
- `backend/api/routes_chat.py`
- `backend/api/routes_artifacts.py`
- `backend/api/routes_data.py`
- `backend/schemas/*`

Application service:

- `src/application/__init__.py`
- `src/application/schemas.py`
- `src/application/chat_service.py`

Frontend:

- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/index.html`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/types/api.ts`
- `frontend/src/components/*`
- `frontend/src/features/*`
- `frontend/src/hooks/useLocalStorage.ts`
- `frontend/src/styles/app.css`
- `frontend/src/test/setup.ts`

Scripts:

- `start-backend.ps1`
- `start-frontend.ps1`
- `start-web.ps1`

Docs/tests:

- `docs/WEB_MIGRATION_AUDIT.md`
- `docs/WEB_ARCHITECTURE.md`
- `docs/WEB_MIGRATION_REPORT.md`
- `tests/test_web_api.py`
- frontend Vitest tests.

## Endpoints

- `GET /api/health`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`
- `POST /api/conversations/{id}/reset-context`
- `POST /api/conversations/{id}/messages`
- `GET /api/artifacts/{artifact_id}/download`
- `GET /api/data/status`
- `POST /api/data/reload`

## Core Reuse

Reused unchanged for computation:

- dynamic Excel loader
- parquet cache
- DuckDB analytical layer
- data catalog
- hybrid router
- deterministic planner
- Qwen/Ollama planner
- QueryPlan validation
- safe SQL builder
- clarification/refusal/safe failure modes
- SQLite conversation memory
- multi-turn state
- semantic matching
- chart/report/export data

## Query Result Changes

No intentional query-result changes were made for frontend compatibility.

The new service serializes output differently for the web, but it still calls the same planner/executor/rendering/export layers.

## Conversation Persistence

Conversation persistence remains backend-owned through `ConversationMemoryService` and SQLite at `data/app_memory.db`.

The browser stores only UI preferences and the selected conversation id.

## Tests

Backend:

- API health.
- Conversation create/list/get/patch/delete/reset.
- Send message contract.
- Invalid payload.
- Invalid conversation.
- Data status/reload.
- Artifact download safety.

Frontend:

- Render conversation.
- Send message.
- Render scalar.
- Render table.
- Render chart.
- Render clarification.
- Render refusal.
- Render error.
- Download action.
- Debug panel.

Executed in this session:

- `python -m compileall app.py backend src`: passed.
- `python -m pytest -q`: 57 passed, 1 Starlette/httpx deprecation warning.
- `npm test`: 5 passed.
- `npm run build`: passed. Vite emitted a non-blocking chunk-size warning because Recharts is bundled.
- `npm audit`: 0 vulnerabilities.

## Integration Smoke

Live services were started on:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- Streamlit fallback: `http://localhost:8501`

Verified:

- `GET /api/health` returned status ok with `qwen3.5:9b`.
- Created conversation through API.
- Sent deterministic query: `May nao downtime cao nhat?`.
- Sent follow-up chart request: `Ve top 5`.
- Sent report request: `Xuat bao cao phan tich downtime`.
- Report response produced 2 downloads.
- Artifact download returned HTTP 200.
- React app rendered in browser with sidebar, composer, table response, and download actions.
- Streamlit fallback still returned HTTP 200.

## Known Issues

- Full end-to-end browser integration against a live FastAPI + Vite stack still depends on local Node dependencies and running servers.
- Historical assistant messages reload as stored text summaries, not full rich response payloads, because the existing SQLite turn schema stores summary/query metadata rather than the full UI payload.
- Streamlit remains available and still has its own fallback rendering components.

## Demo Readiness

Demo readiness: READY FOR LOCAL DEMO with the known limitations below.

- Backend/API unit tests pass.
- Frontend component and send-flow tests pass.
- Live API smoke passed for query, follow-up chart, report export, and artifact download.
- Streamlit fallback still runs.
- React + FastAPI can be started with `.\start-web.ps1`.
