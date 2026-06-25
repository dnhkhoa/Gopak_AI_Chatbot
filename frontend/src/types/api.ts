export type ResponseType =
  | "text"
  | "analysis"
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
  x_axis_unit?: string | null;
  y_axis_unit?: string | null;
  tooltip_unit?: string | null;
  source_result_id?: string | null;
  source_turn_id?: string | null;
  metric?: string | null;
  dimension?: string | null;
}

export interface DashboardPayload {
  cards: Record<string, unknown>[];
  table?: TablePayload | null;
  chart?: ChartPayload | null;
}

export interface KpiCard {
  label: string;
  value: string;
  unit?: string | null;
  hint?: string | null;
}

export interface SourcePayload {
  name: string;
  rows?: number | null;
}

export interface SourceInfo {
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

export interface AnalysisInsight {
  text: string;
  evidence: string[];
}

export interface AnalysisPayload {
  headline: string;
  summary: string;
  insights: AnalysisInsight[];
  table?: TablePayload | null;
}

export interface PublicReportSection {
  section_type: string;
  title: string;
  summary?: string | null;
  kpis: KpiCard[];
  table?: TablePayload | null;
  chart?: ChartPayload | null;
  commentary: string[];
}

export interface ReportPayload {
  report_id: string;
  root_report_id?: string;
  parent_report_id?: string | null;
  revision_number?: number;
  title: string;
  report_type?: string;
  audience?: string;
  detail_level?: string;
  target_page_range?: string;
  subtitle?: string | null;
  source_file_name: string;
  date_range?: Record<string, unknown> | null;
  generated_at: string;
  executive_summary: string[];
  kpis: KpiCard[];
  sections: PublicReportSection[];
  source: SourceInfo;
  filters: Record<string, unknown>[];
  limitations: string[];
  pdf_status: string;
  pdf_download_url?: string | null;
  completeness: Record<string, unknown>;
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
  analysis?: AnalysisPayload | null;
  report?: ReportPayload | null;
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
  source_file_id?: string | null;
  source_file_name?: string | null;
  source_file_sha256?: string | null;
  source_catalog_version?: string | null;
  source_available?: boolean;
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

export type ComponentHealth = "HEALTHY" | "DEGRADED" | "UNAVAILABLE" | "NOT_REQUIRED";

export interface ServiceHealth {
  core_api: ComponentHealth;
  database: ComponentHealth;
  file_catalog: ComponentHealth;
  analytics_engine: ComponentHealth;
  language_model: ComponentHealth;
  report_export: ComponentHealth;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  ollama_available: boolean;
  model: string;
  database_available: boolean;
  memory_available: boolean;
  components?: ServiceHealth;
  infrastructure_degraded?: boolean;
  language_model_available?: boolean;
  banner_message?: string | null;
  language_model_note?: string | null;
}
