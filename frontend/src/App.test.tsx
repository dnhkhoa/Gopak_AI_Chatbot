import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

const conversation = {
  id: "c1",
  title: "Cuộc trò chuyện",
  created_at: "2026-06-21T00:00:00Z",
  updated_at: "2026-06-21T00:00:00Z",
  status: "active"
};

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/health")) {
      return Response.json({ status: "ok", ollama_available: true, model: "qwen3.5:9b", database_available: true, memory_available: true });
    }
    if (url.endsWith("/conversations") && init?.method === "POST") {
      return Response.json(conversation, { status: 201 });
    }
    if (url.endsWith("/conversations")) {
      return Response.json([conversation]);
    }
    if (url.endsWith("/conversations/c1")) {
      return Response.json({ ...conversation, messages: [] });
    }
    if (url.endsWith("/conversations/c1/messages")) {
      return Response.json({
        message_id: "m2",
        conversation_id: "c1",
        response_type: "scalar",
        title: "Tổng thời gian downtime",
        summary: "Tương đương 82 ngày.",
        primary_value: "1.989,56 giờ",
        secondary_value: null,
        table: null,
        chart: null,
        dashboard: null,
        sources: [],
        filters: [],
        downloads: [],
        metadata: { execution_mode: "DETERMINISTIC" }
      });
    }
    return Response.json({}, { status: 404 });
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("loads a conversation and sends a message", async () => {
  render(<App />);
  const input = await screen.findByLabelText("Tin nhắn");
  await userEvent.type(input, "Tổng downtime là bao nhiêu?");
  await userEvent.click(screen.getByLabelText("Gửi"));
  expect(await screen.findByText("1.989,56 giờ")).toBeInTheDocument();
  await waitFor(() => expect(fetch).toHaveBeenCalled());
});
