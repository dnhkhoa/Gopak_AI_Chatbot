# Frontend Progress — Gopak

Mode: `VITE_API_MODE` = `real` (FastAPI) | `mock` (in-browser fixtures).
"Real API integrated" = wired to a backend endpoint that **exists today**.

| Feature | Mock complete | Real API integrated | Tested | Notes |
|---|:---:|:---:|:---:|---|
| App shell + sidebar + brand/logo | ✅ | ✅ | ✅ | i-Soft logo `frontend/src/assets/isoft-logo.png` |
| New chat | ✅ | ✅ | ✅ | `POST /conversations` |
| History list (load) | ✅ | ✅ | ✅ | `GET /conversations`; survives refresh in real mode |
| Open conversation | ✅ | ✅ | ✅ | `GET /conversations/{id}` |
| Rename conversation | ✅ | ✅ | ⚠️ | inline edit → `PATCH`; covered indirectly |
| Delete conversation | ✅ | ✅ | ⚠️ | confirm dialog → `DELETE` |
| Send message / follow-up | ✅ | ✅ | ✅ | `POST …/messages`; memory lives in backend |
| Text response | ✅ | ✅ | ✅ | |
| Scalar response | ✅ | ✅ | ✅ | not a one-cell table |
| Table response | ✅ | ✅ | ✅ | sticky header, scroll |
| Chart response | ✅ | ✅ | ✅ | Recharts, pastel palette, from backend JSON |
| Dashboard response | ✅ | ✅ | ⚠️ | KPI cards + chart/table |
| Data overview | ✅ | ✅ | ✅ | dataset list (not downtime scalar) |
| Schema | ✅ | ✅ | ✅ | |
| Sample rows | ✅ | ✅ | ✅ | |
| Data quality | ✅ | ✅ | ✅ | |
| Clarification | ✅ | ✅ | ✅ | renders as assistant message |
| Refusal | ✅ | ✅ | ✅ | scope explanation, not error |
| Error / safe failure | ✅ | ✅ | ✅ | friendly, no stack trace |
| Sources & filters disclosure | ✅ | ✅ | ✅ | collapsed by default |
| Artifact downloads (HTML/Excel) | ✅ | ✅ | ⚠️ | by artifact ID; real download needs real artifacts |
| Uploaded files panel (list/totals/status) | ✅ | ✅ | ✅ | `/api/files*` implemented; card items + details popover + ⋮ menu |
| Upload `.xlsx` (composer + panel) | ✅ | ✅ | ✅ | `.xlsx` extension and MIME validated server-side |
| File status polling | ✅ | ✅ | ✅ | poll `GET /files/{id}/status` |
| Remove file | ✅ | ✅ | ✅ | confirm when Ready |
| Retry failed upload | ✅ | ❌ | ⚠️ | |

Legend: ✅ done · ⚠️ partial / indirect coverage · ❌ not available.

## Honest status
- **Conversations, messages and all response renderers are integrated against real,
  existing backend endpoints.** History and follow-up memory work in real mode and persist
  across refresh (backend-owned).
- **File upload/list/status/delete are now wired in real mode.** Backend endpoints exist
  and persist upload metadata. Dynamic ingestion of uploaded workbooks into the analytics
  catalog is still a backend follow-up.
- Settings/Debug intentionally absent (per brief §15).
- Tech note: Tailwind/shadcn/TanStack Query/React Router from the suggested stack were
  **not** adopted this round to avoid destabilizing the working app; styling uses a CSS
  design-token layer (`tokens.css`) and data fetching uses a typed adapter + hooks. Flagged
  as an optional follow-up.

## Tests
`npm test -- --run` → 5 files / 18 tests passing (App flow, response components, mock
adapter, `.xlsx`-only upload rule, and the redesigned files panel: Excel icon, long-name
truncation+tooltip, select/reselect, Enter→details, ⋮ menu remove with/without
confirmation, status rendering). `npm run build` passes.
