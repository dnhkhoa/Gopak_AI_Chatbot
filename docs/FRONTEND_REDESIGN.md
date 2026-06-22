# Frontend UI Redesign — Gopak (fe-ui-redesign)

Pastel, ChatGPT-style redesign of the existing React + Vite + TypeScript frontend.
Scope of this change: **frontend only** (`frontend/`). No backend, pipeline, evaluation
or data-processing code was modified.

## What changed

| Area | File | Change |
|------|------|--------|
| Design tokens + full styling | `frontend/src/styles/app.css` | Rewritten with the chốt pastel palette (page `#F8F8FB`, sidebar `#F1F3F7`, surface `#FFFFFF`, user bubble `#EEF2FF`, border `#E5E7EF`, primary blue `#356FD8`, soft primary `#AEBCE8`, soft green `#C8DCC8`, text `#20263A`, muted `#747B8C`, success `#18B76A`). Soft borders/shadows, medium radius, generous spacing. Density + font-size tokens via `<html data-density / data-font>`. |
| Brand + sidebar | `frontend/src/features/conversations/ConversationSidebar.tsx` | Real i-Soft logo + divider + `Gopak` brand chip; `New chat` primary button; single `History` group; per-item ⋯ menu with **Rename** (inline edit, saved to backend via `PATCH`) and **Delete** (confirmation). Removed the customer-facing **Debug** toggle and the global reset/delete buttons. |
| App shell / state | `frontend/src/App.tsx` | Wired `renameConversation`; delete only re-selects when the active chat is removed; empty state shows logo + "Tôi có thể giúp gì cho bạn?" + subtitle; animated "Đang phân tích…" indicator; composer docked in a gradient `composer-wrap`. Debug capability gated behind `VITE_ENABLE_DEVELOPER_TOOLS` (default **false**). |
| Assistant messages | `frontend/src/components/ChatMessage.tsx` | Small consistent assistant avatar (soft-green circle) + lightweight content column (no heavy card). All existing response types preserved. |
| Composer | `frontend/src/features/chat/ChatComposer.tsx` | Round **up-arrow** send button, auto-grow textarea, Enter sends / Shift+Enter newline, empty placeholder, disabled while sending. |
| Env | `frontend/.env`, `frontend/.env.example` | `VITE_API_BASE_URL=http://127.0.0.1:8000/api`, `VITE_ENABLE_DEVELOPER_TOOLS=false`. |

## Logo asset

- Source: `Logo iSoft 1/iSOFT_LOGO-original.png` (full color wordmark; the
  `-nobackground` export was incomplete, only a stray glyph).
- Copied to: **`frontend/src/assets/isoft-logo.png`**.
- Rendered at fixed height (22px header / 34px empty-state), width auto — aspect
  ratio preserved, not cropped, `alt="i-Soft"`.

## Response types rendered (unchanged contract)

text, scalar, table, chart, dashboard, data_overview, schema, sample_table,
data_quality, clarification, refusal, error — all kept and styled with shared tokens.
Charts use the pastel palette; tables have sticky headers, horizontal scroll and row limits.

## Verification

- `npm test -- --run` → **6/6 passing** (App flow + all response components).
- `npm run build` → **success** (`tsc -b && vite build`, logo bundled, CSS 11.9 kB).
- `npm run dev` → boots on `http://127.0.0.1:5173/` (HTTP 200).

## Out of scope (not done — requires backend work the brief forbids touching)

The larger migration spec asked for an Uploaded-files panel, a Settings page
(General/Appearance/Data Files) with server persistence, React Router, shadcn/ui and
TanStack Query. The current backend exposes only `health`, `conversations`, `chat`,
`artifacts` and `data` — there are **no** `/api/files` or `/api/settings` endpoints.
Per the brief ("only edit `frontend/`", "do not mock"), these were intentionally **not**
faked. They need backend endpoints first; flag for a follow-up that includes backend scope.
