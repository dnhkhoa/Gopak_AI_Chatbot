import type { ChatResponse, ConversationDetail, ConversationPayload, ResponseType } from "../types/api";
import type { UploadedFile } from "../types/files";

// Presentation-only fixtures. NO analytics, aggregation or SQL here — these are
// canned backend responses used purely to develop and demo the UI renderers.

const now = "2026-06-22T00:00:00Z";

export const mockHealth = {
  status: "ok" as const,
  ollama_available: true,
  model: "qwen3.5:9b",
  database_available: true,
  memory_available: true
};

export const mockConversations: ConversationPayload[] = [
  { id: "conv-1", title: "Top machines by downtime", created_at: now, updated_at: now, status: "active" },
  { id: "conv-2", title: "Loss assignment overview", created_at: now, updated_at: now, status: "active" },
  {
    id: "conv-3",
    title: "A very long conversation title that should be truncated with an ellipsis in the sidebar",
    created_at: now,
    updated_at: now,
    status: "active"
  }
];

export const mockFiles: UploadedFile[] = [
  { id: "file-1", filename: "Machine_Downtime_20260203_100753.xlsx", size_bytes: 2_516_582, status: "ready", uploaded_at: now },
  { id: "file-2", filename: "Loss_Assignment_20260203_100840.xlsx", size_bytes: 1_887_436, status: "ready", uploaded_at: now },
  { id: "file-3", filename: "EntryTransaction_20260203_164943.xlsx", size_bytes: 3_250_585, status: "ready", uploaded_at: now }
];

function base(responseType: ResponseType, conversationId: string, overrides: Partial<ChatResponse>): ChatResponse {
  return {
    message_id: `msg-${Math.round(performance.now())}-${responseType}`,
    conversation_id: conversationId,
    response_type: responseType,
    title: "",
    summary: "",
    primary_value: null,
    secondary_value: null,
    table: null,
    chart: null,
    dashboard: null,
    sources: [],
    filters: [],
    downloads: [],
    metadata: { execution_mode: "DETERMINISTIC", llm_called: false, latency_ms: { total: 104 } },
    ...overrides
  };
}

/** Build a representative response for a given keyword-selected type (mock only). */
export function buildMockResponse(conversationId: string, message: string): ChatResponse {
  const q = message.toLowerCase();

  if (/\b(overview|datasets?|what data|data có gì|nội dung)\b/.test(q)) {
    return base("data_overview", conversationId, {
      title: "Loaded datasets",
      summary: "The workspace currently holds 3 datasets.",
      table: {
        columns: ["Dataset", "Rows", "Key columns", "Date range"],
        rows: [
          { Dataset: "Machine downtime", Rows: "9,151", "Key columns": "machine, downtime_hours, date", "Date range": "2025-01 → 2026-02" },
          { Dataset: "Loss assignment", Rows: "4,210", "Key columns": "line, loss_type, hours", "Date range": "2025-01 → 2026-02" },
          { Dataset: "Entry transaction", Rows: "12,894", "Key columns": "entry_id, qty, timestamp", "Date range": "2025-03 → 2026-02" }
        ]
      },
      sources: [{ name: "Machine_Downtime.xlsx", rows: 9151 }]
    });
  }

  if (/\b(schema|columns?|cấu trúc)\b/.test(q)) {
    return base("schema", conversationId, {
      title: "Schema — Machine downtime",
      summary: "5 columns.",
      table: {
        columns: ["Column", "Type", "Nullable", "Description"],
        rows: [
          { Column: "machine", Type: "VARCHAR", Nullable: "no", Description: "Machine identifier" },
          { Column: "downtime_hours", Type: "DOUBLE", Nullable: "no", Description: "Downtime in hours" },
          { Column: "date", Type: "DATE", Nullable: "no", Description: "Event date" },
          { Column: "shift", Type: "VARCHAR", Nullable: "yes", Description: "Work shift" },
          { Column: "reason", Type: "VARCHAR", Nullable: "yes", Description: "Stoppage reason" }
        ]
      }
    });
  }

  if (/\b(sample|first \d+ rows|dòng mẫu)\b/.test(q)) {
    return base("sample_table", conversationId, {
      title: "Sample rows — Machine downtime",
      summary: "First 3 rows.",
      table: {
        columns: ["machine", "downtime_hours", "date"],
        rows: [
          { machine: "MX-01", downtime_hours: 41.2, date: "2026-02-01" },
          { machine: "MX-02", downtime_hours: 12.8, date: "2026-02-01" },
          { machine: "MX-03", downtime_hours: 7.5, date: "2026-02-02" }
        ]
      }
    });
  }

  if (/\b(quality|missing|null|chất lượng)\b/.test(q)) {
    return base("data_quality", conversationId, {
      title: "Data quality — Machine downtime",
      summary: "2 issues detected.",
      table: {
        columns: ["Check", "Column", "Affected rows"],
        rows: [
          { Check: "Null values", Column: "reason", "Affected rows": "318" },
          { Check: "Negative values", Column: "downtime_hours", "Affected rows": "4" }
        ]
      }
    });
  }

  if (/\b(chart|plot|graph|biểu đồ|top \d)\b/.test(q)) {
    return base("chart", conversationId, {
      title: "Top 5 machines by downtime",
      summary: "Machine MX-01 recorded the highest total downtime.",
      chart: {
        type: "bar",
        title: "Top 5 machines by downtime",
        x_key: "machine",
        y_keys: ["total_downtime_hours"],
        data: [
          { machine: "MX-01", total_downtime_hours: 413.6 },
          { machine: "MX-07", total_downtime_hours: 388.1 },
          { machine: "MX-03", total_downtime_hours: 256.4 },
          { machine: "MX-12", total_downtime_hours: 201.9 },
          { machine: "MX-05", total_downtime_hours: 188.3 }
        ]
      },
      sources: [{ name: "Machine_Downtime.xlsx · Report", rows: 9151 }],
      filters: [{ label: "metric", operator: "=", value: "total_downtime_hours" }],
      downloads: [{ id: "report-top5.html", label: "Download HTML report", filename: "report.html", mime_type: "text/html" }]
    });
  }

  if (/\b(table|list|breakdown|bảng)\b/.test(q)) {
    return base("table", conversationId, {
      title: "Downtime by machine",
      summary: "Sorted by total downtime, descending.",
      table: {
        columns: ["Machine", "Total downtime (h)", "Stoppages"],
        rows: [
          { Machine: "MX-01", "Total downtime (h)": "413.57", Stoppages: "128" },
          { Machine: "MX-07", "Total downtime (h)": "388.10", Stoppages: "97" },
          { Machine: "MX-03", "Total downtime (h)": "256.42", Stoppages: "76" }
        ]
      },
      downloads: [{ id: "result.xlsx", label: "Download Excel result", filename: "result.xlsx", mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }]
    });
  }

  if (/\b(dashboard|kpi|summary)\b/.test(q)) {
    return base("dashboard", conversationId, {
      title: "Downtime dashboard",
      summary: "Key indicators for the current dataset.",
      dashboard: {
        cards: [
          { label: "Total downtime", value: "1,989.56 h" },
          { label: "Machines", value: "24" },
          { label: "Stoppages", value: "1,204" }
        ],
        chart: {
          type: "bar",
          title: "Top machines",
          x_key: "machine",
          y_keys: ["total_downtime_hours"],
          data: [
            { machine: "MX-01", total_downtime_hours: 413.6 },
            { machine: "MX-07", total_downtime_hours: 388.1 }
          ]
        },
        table: null
      }
    });
  }

  if (/\b(best machine|ambiguous|which|làm rõ)\b/.test(q)) {
    return base("clarification", conversationId, {
      title: "Clarification",
      summary: 'Do you want "best machine" to mean the lowest total downtime or the fewest stoppages?'
    });
  }

  if (/\b(revenue|profit|sales|doanh thu)\b/.test(q)) {
    return base("refusal", conversationId, {
      title: "Out of scope",
      summary: "The current data does not contain revenue information."
    });
  }

  if (/\b(error|fail|broken)\b/.test(q)) {
    return base("error", conversationId, {
      title: "Something went wrong",
      summary: "We couldn't complete that request. Please try again."
    });
  }

  // Default: scalar.
  return base("scalar", conversationId, {
    title: "Total downtime",
    summary: "Equivalent to 82 days, 21 hours, 33 minutes.",
    primary_value: "1,989.56 hours",
    sources: [{ name: "Machine_Downtime.xlsx · Report", rows: 9151 }],
    downloads: [{ id: "report.html", label: "Download HTML report", filename: "report.html", mime_type: "text/html" }]
  });
}

export const emptyConversationDetail = (conversation: ConversationPayload): ConversationDetail => ({
  ...conversation,
  messages: []
});
