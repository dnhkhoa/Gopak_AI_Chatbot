# React + FastAPI Web Architecture

Updated: 2026-06-21

## Target Runtime

```text
React + Vite + TypeScript
        ↓ HTTP JSON
FastAPI backend
        ↓
ChatApplicationService
        ↓
Existing hybrid query pipeline
        ├── deterministic planner
        ├── real LLM planner
        ├── clarification/refusal/safe failure
        ├── DuckDB/parquet analytical layer
        └── SQLite conversation memory
```

## Backend

FastAPI lives under `backend/`.

Routes:

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

Safety decisions:

- CORS is limited to the configured local frontend origin.
- Pydantic validates chat message length and conversation payloads.
- The frontend never sends SQL or QueryPlan.
- Download routes accept artifact IDs only and validate files inside `reports/`.
- Stack traces are not returned to clients.

## Shared Application Service

`src/application/` contains:

- `schemas.py`: API-safe Pydantic models.
- `chat_service.py`: shared orchestration layer.

Both Streamlit and FastAPI use this service. Query results are computed by the same core pipeline, so React and Streamlit do not fork business behavior.

## Frontend

React lives under `frontend/`.

Important files:

- `src/api/client.ts`: single API base URL and fetch wrapper.
- `src/types/api.ts`: TypeScript contract matching `src/application/schemas.py`.
- `src/features/conversations/ConversationSidebar.tsx`
- `src/features/chat/ChatComposer.tsx`
- `src/components/ChatMessage.tsx`
- `src/components/ScalarResult.tsx`
- `src/components/DataTable.tsx`
- `src/components/ChartResult.tsx`
- `src/components/DashboardResult.tsx`
- `src/components/ClarificationMessage.tsx`
- `src/components/RefusalMessage.tsx`
- `src/components/ErrorMessage.tsx`
- `src/components/SourceDetails.tsx`
- `src/components/DownloadActions.tsx`
- `src/components/DebugPanel.tsx`

Browser local storage contains only:

- selected conversation id
- debug preference
- sidebar collapsed state

Conversation state and analytical memory remain in backend SQLite.

## UI

The UI is ChatGPT-like and intentionally quiet:

- Background: `#F8F8FB`
- Sidebar: `#F1F3F7`
- Assistant surface: `#FFFFFF`
- User message: `#EEF2FF`
- Border: `#E5E7EF`
- Primary pastel: `#AEBCE8`
- Secondary pastel: `#C8DCC8`
- Text: `#30323A`
- Muted text: `#7A7E89`

No raw JSON is shown in normal mode. Debug metadata is behind the Debug toggle.

## Running

Backend:

```powershell
.\start-backend.ps1
```

Frontend:

```powershell
.\start-frontend.ps1
```

Both:

```powershell
.\start-web.ps1
```

Streamlit fallback:

```powershell
streamlit run app.py
```
