// Chat-related response types. Re-exported from api.ts which is the canonical
// definition matching the FastAPI backend (snake_case).
export type {
  ResponseType,
  TablePayload,
  ChartPayload,
  DashboardPayload,
  SourcePayload,
  FilterPayload,
  DownloadPayload,
  ChatResponse,
  UiMessage
} from "./api";
