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
  expect(screen.getByText("Nguồn và bộ lọc")).toBeInTheDocument();
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
