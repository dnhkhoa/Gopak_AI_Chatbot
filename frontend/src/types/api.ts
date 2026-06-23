export type ResponseType =
  | "text"
  | "scalar"
  | "table"
  | "chart"
  | "dashboard"
  | "clarification"
  | "refusal"
  | "error"
  | "report"
  | "data_overview"
  | "schema"
  | "sample_table"
  | "data_quality"
  | "record_detail"
  | "record_table"
  | "timeline";

export interface TablePayload {
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface ChartPayload {
  type: "bar" | "horizontal_bar" | "line" | "pie";
  title: string;
  x_key: string;
  y_keys: string[];
  data: Record<string, unknown>[];
}

export interface DashboardPayload {
  cards: Record<string, unknown>[];
  table?: TablePayload | null;
  chart?: ChartPayload | null;
}

export interface SourcePayload {
  name: string;
  rows?: number | null;
}

export interface FilterPayload {
  label: string;
  operator: string;
  value?: unknown;
}

export interface DownloadPayload {
  id: string;
  label: string;
  filename: string;
  mime_type: string;
}

export interface ChatResponse {
  message_id: string;
  conversation_id: string;
  response_type: ResponseType;
  title: string;
  summary: string;
  primary_value?: string | null;
  secondary_value?: string | null;
  table?: TablePayload | null;
  chart?: ChartPayload | null;
  dashboard?: DashboardPayload | null;
  sources: SourcePayload[];
  filters: FilterPayload[];
  downloads: DownloadPayload[];
  metadata: Record<string, unknown>;
}

export interface ConversationPayload {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: string;
  active_file_id?: string | null;
  active_file_name?: string | null;
}

export interface ConversationMessage {
  id?: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string | null;
  execution_mode?: string | null;
  response?: ChatResponse | null;
}

export interface ConversationDetail extends ConversationPayload {
  messages: ConversationMessage[];
}

export interface ActiveFilePayload {
  conversation_id: string;
  active_file_id?: string | null;
  active_file_name?: string | null;
  status: string;
}

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  ollama_available: boolean;
  model: string;
  database_available: boolean;
  memory_available: boolean;
}
