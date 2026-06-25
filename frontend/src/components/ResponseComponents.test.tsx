import { render, screen } from "@testing-library/react";
import { ChatMessage } from "./ChatMessage";
import type { ChatResponse, UiMessage } from "../types/api";

const baseResponse: ChatResponse = {
  message_id: "m1",
  conversation_id: "c1",
  response_type: "scalar",
  title: "Tổng thời gian downtime",
  summary: "Tương đương 82 ngày.",
  primary_value: "1.989,56 giờ",
  secondary_value: null,
  table: null,
  chart: null,
  dashboard: null,
  sources: [{ name: "Machine_Downtime.xlsx · Report", rows: 9151 }],
  filters: [],
  downloads: [{ id: "report.html", label: "Tải HTML", filename: "report.html", mime_type: "text/html" }],
  metadata: { execution_mode: "DETERMINISTIC" }
};

function assistant(response: ChatResponse): UiMessage {
  return { id: response.message_id, role: "assistant", content: response.summary, response };
}

test("renders scalar, sources, download and debug", () => {
  render(<ChatMessage message={assistant(baseResponse)} debug />);
  expect(screen.getByText("1.989,56 giờ")).toBeInTheDocument();
  expect(screen.getByText("Sources and filters")).toBeInTheDocument();
  expect(screen.getByText("Tải HTML")).toBeInTheDocument();
  expect(screen.getByText("Debug")).toBeInTheDocument();
});

test("renders table response", () => {
  render(
    <ChatMessage
      debug={false}
      message={assistant({
        ...baseResponse,
        response_type: "table",
        title: "Top máy",
        summary: "Máy 11 cao nhất.",
        primary_value: null,
        table: { columns: ["Máy", "Thời lượng"], rows: [{ Máy: "Máy 11", "Thời lượng": "413,57 giờ" }] },
        downloads: []
      })}
    />
  );
  expect(screen.getByText("Máy 11")).toBeInTheDocument();
  expect(screen.getByText("413,57 giờ")).toBeInTheDocument();
});

test("renders chart response", () => {
  render(
    <ChatMessage
      debug={false}
      message={assistant({
        ...baseResponse,
        response_type: "chart",
        title: "Biểu đồ",
        summary: "",
        primary_value: null,
        chart: { type: "bar", title: "Biểu đồ", x_key: "Máy", y_keys: ["Thời lượng"], data: [{ Máy: "Máy 11", "Thời lượng": 100 }] },
        downloads: []
      })}
    />
  );
  expect(screen.getByText("Biểu đồ")).toBeInTheDocument();
});

test("does not render invalid single-character analysis narrative", () => {
  render(
    <ChatMessage
      debug={false}
      message={assistant({
        ...baseResponse,
        response_type: "analysis",
        title: "Phân tích",
        summary: "D",
        primary_value: null,
        analysis: { headline: "Phân tích dữ liệu", summary: "D", insights: [], table: null },
        downloads: []
      })}
    />
  );
  expect(screen.queryByText("D")).not.toBeInTheDocument();
});

test("dispatches report payload to PDF-only ReportPreview even when chart exists", () => {
  const reportResponse: ChatResponse = {
    ...baseResponse,
    response_type: "report",
    title: "Báo cáo phân tích downtime",
    summary: "Báo cáo đã tổng hợp dữ liệu downtime.",
    primary_value: null,
    chart: { type: "line", title: "Xu hướng", x_key: "Ngày", y_keys: ["Tổng downtime"], data: [{ Ngày: "2026-01-01", "Tổng downtime": 10 }] },
    report: {
      report_id: "r1",
      title: "Báo cáo phân tích downtime",
      subtitle: "Báo cáo mô tả dữ liệu downtime.",
      source_file_name: "Machine_Downtime.xlsx",
      date_range: { from: "2026-01-01", to: "2026-01-31" },
      generated_at: "09:00, ngày 25/06/2026",
      executive_summary: ["Báo cáo đã tổng hợp dữ liệu downtime theo các section chính."],
      kpis: [{ label: "Tổng downtime", value: "10", unit: "giờ", hint: "Tính từ file đang chọn." }],
      source: { name: "Machine_Downtime.xlsx", rows: 9151 },
      filters: [],
      limitations: ["Kết quả là mô tả dữ liệu đã import."],
      pdf_status: "ready",
      pdf_download_url: "/api/artifacts/report_r1.pdf/download",
      completeness: { requested_sections: 8, backend_sections: 8, rendered_sections: 8, missing_sections: [] },
      sections: [
        { section_type: "tong_quan_du_lieu", title: "Tổng quan dữ liệu", summary: "File có dữ liệu downtime đã import.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "tong_downtime", title: "KPI tổng downtime", summary: "Tổng downtime là 10 giờ.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "so_lan_dung", title: "KPI số lần dừng", summary: "Dữ liệu có nhiều lần dừng.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "top_may", title: "Top máy", summary: "Máy 11 đứng đầu theo downtime.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "top_nguyen_nhan", title: "Top nguyên nhân", summary: "Nguyên nhân chính có downtime cao.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "xu_huong", title: "Biểu đồ xu hướng", summary: "Xu hướng downtime theo ngày.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "nhan_xet_quan_ly", title: "Nhận xét quản lý", summary: "Nên xem đồng thời downtime và số lần dừng.", kpis: [], table: null, chart: null, commentary: [] },
        { section_type: "nguon_va_gioi_han", title: "Nguồn và giới hạn", summary: "Báo cáo dùng file đang chọn.", kpis: [], table: null, chart: null, commentary: [] }
      ]
    },
    downloads: [{ id: "report_r1.pdf", label: "Tải báo cáo PDF", filename: "report_r1.pdf", mime_type: "application/pdf" }]
  };
  render(<ChatMessage debug={false} message={assistant(reportResponse)} />);
  expect(screen.getByTestId("report-preview")).toBeInTheDocument();
  expect(document.querySelectorAll("[data-section-type]").length).toBe(8);
  expect(screen.getByText("Tải báo cáo PDF")).toBeInTheDocument();
  expect(screen.queryByText("Tải HTML")).not.toBeInTheDocument();
  expect(screen.queryByText("Tải Excel")).not.toBeInTheDocument();
  expect(document.querySelector(".chart-box")).not.toBeInTheDocument();
});

test("renders clarification, refusal and error states", () => {
  const { rerender } = render(
    <ChatMessage debug={false} message={assistant({ ...baseResponse, response_type: "clarification", summary: "Bạn muốn phân tích theo gì?" })} />
  );
  expect(screen.getByText("Bạn muốn phân tích theo gì?")).toBeInTheDocument();
  rerender(<ChatMessage debug={false} message={assistant({ ...baseResponse, response_type: "refusal", summary: "Không có dữ liệu phù hợp." })} />);
  expect(screen.getByText("Không có dữ liệu phù hợp.")).toBeInTheDocument();
  rerender(<ChatMessage debug={false} message={assistant({ ...baseResponse, response_type: "error", summary: "Không thể kết nối." })} />);
  expect(screen.getByText("Không thể kết nối.")).toBeInTheDocument();
});

test("renders metadata response types", () => {
  const metadataResponse: ChatResponse = {
    ...baseResponse,
    response_type: "data_overview",
    title: "Tổng quan dữ liệu",
    summary: "Hệ thống hiện có 3 bộ dữ liệu.",
    primary_value: null,
    table: { columns: ["Bộ dữ liệu", "Số bản ghi"], rows: [{ "Bộ dữ liệu": "Downtime máy", "Số bản ghi": "9.151" }] },
    downloads: []
  };
  const { rerender } = render(<ChatMessage message={assistant(metadataResponse)} debug={false} />);
  expect(screen.getByText("Tổng quan dữ liệu")).toBeInTheDocument();
  expect(screen.getByText("Downtime máy")).toBeInTheDocument();

  rerender(<ChatMessage message={assistant({ ...metadataResponse, response_type: "schema", title: "Schema dữ liệu" })} debug={false} />);
  expect(screen.getByText("Schema dữ liệu")).toBeInTheDocument();

  rerender(<ChatMessage message={assistant({ ...metadataResponse, response_type: "sample_table", title: "5 dòng mẫu" })} debug={false} />);
  expect(screen.getByText("5 dòng mẫu")).toBeInTheDocument();

  rerender(<ChatMessage message={assistant({ ...metadataResponse, response_type: "data_quality", title: "Chất lượng dữ liệu" })} debug={false} />);
  expect(screen.getByText("Chất lượng dữ liệu")).toBeInTheDocument();
});
