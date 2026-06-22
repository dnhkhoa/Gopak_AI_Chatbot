# Frontend Functional Spec — Gopak

Stack: React + Vite + TypeScript, Lucide icons, Recharts, plain CSS design tokens
(`frontend/src/styles/tokens.css`). All static UI is **English**; users may type Vietnamese.
The transport is abstracted behind `GopakApi` with **mock** and **real** modes
(`VITE_API_MODE`). No analytics, SQL, QueryPlan or Excel parsing happens in the browser.

## Screens

### 1. Chat (empty state)
- **Components**: `AppShell` (App.tsx), `ConversationSidebar`, `ChatComposer`, `UploadedFilesPanel`.
- **User action**: open app / start `New chat`.
- **API**: `GET /conversations`, `POST /conversations` (if none), `GET /health`, `GET /files`.
- **Empty state**: i-Soft logo + "How can I help you?" + "Ask questions about your data." No header, no dashboard, no technical text.
- **Loading**: "Loading…" placeholder while bootstrapping.
- **Error**: "Unable to reach the analysis service." with Retry.
- **Acceptance**: no Vietnamese static labels; no Settings/Debug; composer shows upload (↑ from line) + textarea + send (↑).

### 2. Chat (active conversation)
- **Components**: `ChatMessage` (user bubble / assistant + avatar), per-type renderers, `SourceDetails`, `DownloadActions`.
- **User action**: type a question, Enter to send (Shift+Enter = newline).
- **API**: `POST /conversations/{id}/messages` → `ChatResponse`; then `GET /conversations` to refresh titles.
- **Loading**: animated "Analyzing…" indicator; composer disabled while sending.
- **Rendering by `response_type`**: text, scalar, table, chart, dashboard, data_overview, schema, sample_table, data_quality, clarification, refusal, error.
- **Acceptance**: each type uses its own component — never collapsed into a single text/scalar box; data_overview renders a dataset list, not a downtime scalar; clarification/refusal render as normal assistant messages (not error cards).

### 3. Sidebar (history)
- **Components**: `BrandHeader` (logo + "Gopak"), `NewChatButton`, `HistoryList`/`HistoryItem`.
- **User action**: select / rename (inline) / delete (confirm) a conversation.
- **API**: `GET /conversations`, `PATCH /conversations/{id}`, `DELETE /conversations/{id}`.
- **Behaviour**: single `History` group (no Today/Yesterday); long titles use ellipsis + `title` tooltip; list scrolls independently.
- **Acceptance**: history loads from backend (real mode), survives refresh; no Settings/Debug entries.

### 4. Uploaded files panel (fixed lower-right)
- **Components**: `UploadedFilesPanel`, `UploadedFileItem`; upload also available from the composer.
- **User action**: drag-drop or browse `.xlsx`; remove (confirm when Ready); retry on error; collapse/expand.
- **API**: `GET /files`, `POST /files/upload`, `GET /files/{id}/status` (polled), `DELETE /files/{id}`.
- **Statuses**: Uploading → Processing → Ready / Failed (spinner while busy).
- **Loading/Error**: "Loading files…" empty state; friendly alert "Only Excel .xlsx files are supported." with Retry.
- **Acceptance**: only `.xlsx` accepted (accept attr + client filter + server validation); long names ellipsis + tooltip; list scrolls; totals (count + size); no local path; file **ID** used (never path); responsive → bottom drawer on narrow screens.

## Composer
Layout `[Upload ↑] [textarea] [Send ↑]`. No placeholder. Enter sends, Shift+Enter newline.
Upload accepts `.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

## Out of scope this round
Settings, Debug, admin/model panels, auth, multi-user (per brief §15).

## Verification
- `npm test -- --run` — component + hook + mock tests (Sidebar/logo, composer, files panel,
  `.xlsx`-only rule, all response renderers, mock adapter flow).
- `npm run build` — typecheck + production build.
- `VITE_API_MODE=mock npm run dev` — exercise every screen without a backend.
