import { buildMockResponse } from "./fixtures";
import { mockApi } from "./mockApi";

test("buildMockResponse routes keywords to the right response type", () => {
  expect(buildMockResponse("c1", "show loaded datasets overview").response_type).toBe("data_overview");
  expect(buildMockResponse("c1", "show me a chart of top 5").response_type).toBe("chart");
  expect(buildMockResponse("c1", "give me the schema").response_type).toBe("schema");
  expect(buildMockResponse("c1", "what is the revenue").response_type).toBe("refusal");
  expect(buildMockResponse("c1", "which is the best machine").response_type).toBe("clarification");
  expect(buildMockResponse("c1", "total downtime").response_type).toBe("scalar");
});

test("mock api creates, lists and stores conversation turns", async () => {
  const created = await mockApi.createConversation();
  expect(created.title).toBe("New conversation");

  const list = await mockApi.listConversations();
  expect(list.some((c) => c.id === created.id)).toBe(true);

  const response = await mockApi.sendMessage(created.id, "total downtime");
  expect(response.response_type).toBe("scalar");

  const detail = await mockApi.getConversation(created.id);
  expect(detail.messages).toHaveLength(2);
  expect(detail.messages[0].role).toBe("user");
});

test("mock api uploads and removes files", async () => {
  const file = new File([new Uint8Array(1024)], "Test.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  });
  const uploaded = await mockApi.uploadFile(file);
  expect(uploaded.status).toBe("processing");

  await mockApi.deleteFile(uploaded.id);
  const files = await mockApi.listFiles();
  expect(files.some((f) => f.id === uploaded.id)).toBe(false);
});
