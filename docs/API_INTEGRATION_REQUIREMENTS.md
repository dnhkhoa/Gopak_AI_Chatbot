# API Integration Requirements — Gopak Frontend

The frontend depends only on the `GopakApi` contract (`frontend/src/api/contract.ts`).
Two adapters implement it: **real** (FastAPI, `frontend/src/api/*.ts`) and **mock**
(`frontend/src/mocks/mockApi.ts`). Mode is chosen by `VITE_API_MODE` (`real` | `mock`).

Base URL: `VITE_API_BASE_URL` (default `http://127.0.0.1:8000/api`).

| Feature | Method | Endpoint | Request | Response | Backend status | Frontend status |
|---|---|---|---|---|---|---|
| Health | GET | `/health` | – | `{status, ollama_available, database_available, memory_available, model}` | ✅ exists | Integrated (real + mock) |
| List conversations | GET | `/conversations` | – | `ConversationPayload[]` | ✅ exists | Integrated |
| Create conversation | POST | `/conversations` | `{title?}` | `ConversationPayload` | ✅ exists | Integrated |
| Get conversation | GET | `/conversations/{id}` | – | `ConversationDetail` (with `messages[]`) | ✅ exists | Integrated |
| Rename conversation | PATCH | `/conversations/{id}` | `{title}` | `ConversationPayload` | ✅ exists | Integrated |
| Delete conversation | DELETE | `/conversations/{id}` | – | `204` | ✅ exists | Integrated |
| Reset context | POST | `/conversations/{id}/reset-context` | – | `ConversationDetail` | ✅ exists | Client method ready (not surfaced in UI this round) |
| Send message | POST | `/conversations/{id}/messages` | `{message, debug?}` | `ChatResponse` | ✅ exists | Integrated |
| Artifact download | GET | `/artifacts/{artifact_id}/download` | – | file stream | ✅ exists | Integrated (download links) |
| **List files** | GET | `/files` | – | `UploadedFile[]` | ✅ exists | Integrated |
| **Upload file** | POST | `/files/upload` | `multipart/form-data` (`file`, `.xlsx`) | `UploadedFile` | ✅ exists | Integrated |
| **File status** | GET | `/files/{file_id}/status` | – | `UploadedFile` | ✅ exists | Integrated |
| **Delete file** | DELETE | `/files/{file_id}` | – | `204` | ✅ exists | Integrated |

## File Endpoints

The current FastAPI app (`backend/api/`) exposes `health`, `conversations`, `chat`,
`artifacts`, `data`, and `files`. The frontend Uploaded Files panel can run in real mode.
Current backend behavior:

- `POST /api/files/upload` — accepts a single `.xlsx`, validates **extension AND MIME**
  server-side (never trust the client), sanitize the filename, generate an internal
  file ID, saves into the allowed upload dir, checks the workbook is readable, and returns
  `{id, filename, size_bytes, status}`. Dynamic catalog ingestion/registration is still a
  backend follow-up.
- `GET /api/files/{id}/status` — returns `status` ∈ `uploading|processing|ready|failed`
  (+ `error` when failed). On ingestion failure: `status=failed`, do **not** register a
  broken table, do not crash.
- `GET /api/files` — lists previously uploaded files (persisted, so they survive refresh).
- `DELETE /api/files/{id}` — removes the file only after backend confirmation; never exposes
  or accept a local filesystem path.

`UploadedFile` shape expected by the frontend (`frontend/src/types/files.ts`):

```json
{ "id": "string", "filename": "name.xlsx", "size_bytes": 12345,
  "status": "uploading|processing|ready|failed", "error": null, "uploaded_at": "ISO",
  "row_count": 9151, "sheet_count": 1 }
```

`row_count` and `sheet_count` are **optional (BACKEND OPTIONAL)** display-only fields
shown in the File details popover. If the backend can surface them after ingestion
(it already knows row/sheet counts from the DuckDB registration step), please include
them — they are additive and break nothing. When absent, the frontend simply hides those
rows; it never parses Excel to compute them.

Frontend never parses Excel, never computes aggregations, never generates SQL or
QueryPlan. It only renders what the backend returns.

## Updated Upload Readiness Contract

Updated: 2026-06-22

The backend now treats `Ready` as queryable, not just uploaded/readable.

`UploadedFile.status` values:

- `uploaded`
- `uploading` (legacy/mock compatible)
- `processing`
- `ready`
- `failed`
- `deleting`

Frontend may select/use a file only when:

```ts
file.status === "ready" && file.queryable === true
```

Additional additive fields returned by the backend:

```json
{
  "processing_stage": "file_validation|sheet_scanning|parquet_write|catalog_update|query_validation|ready|failed|deleting",
  "progress": 0,
  "queryable": false,
  "row_count": 9151,
  "sheet_count": 1,
  "table_count": 1,
  "ready_at": "ISO",
  "failed_at": "ISO",
  "error": {"code": "READINESS_FAILED", "message": "..."},
  "error_code": "READINESS_FAILED",
  "error_message": "..."
}
```

`POST /api/files/upload` now saves the raw `.xlsx`, runs ingestion, writes parquet/cache/catalog, validates with DuckDB, and then returns `ready` or `failed`.

`PUT /api/conversations/{id}/active-file` returns conflict/error for files that are not `ready && queryable`.

## Endpoint-name confirmations needed

If any existing endpoint differs from the paths above (e.g. message field names, the
`reset-context` path, or the artifact download shape), please confirm — the frontend will
not guess; update this table and the matching `frontend/src/api/*.ts` module.
