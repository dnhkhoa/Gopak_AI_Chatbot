import type { GopakApi } from "../api/contract";
import type { ChatResponse, ConversationDetail, ConversationPayload } from "../types/api";
import type { UploadedFile } from "../types/files";
import { buildMockResponse, mockConversations, mockFiles, mockHealth } from "./fixtures";

// In-memory mock backend. Mirrors the GopakApi contract so UI components are
// identical in mock and real mode. Contains NO analytics — only canned data and
// realistic latency / status transitions to exercise loading & error states.

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

let conversations: ConversationPayload[] = mockConversations.map((c) => ({ ...c }));
const transcripts = new Map<string, ConversationDetail["messages"]>();
let files: UploadedFile[] = mockFiles.map((f) => ({ ...f }));
let seq = 100;
const nextId = (prefix: string) => `${prefix}-${++seq}`;

function touch(id: string) {
  conversations = conversations.map((c) => (c.id === id ? { ...c, updated_at: new Date(0).toISOString() } : c));
}

export const mockApi: GopakApi = {
  async health() {
    await delay(80);
    return mockHealth;
  },

  async listConversations() {
    await delay(120);
    return conversations.map((c) => ({ ...c }));
  },

  async createConversation(title?: string) {
    await delay(120);
    const conversation: ConversationPayload = {
      id: nextId("conv"),
      title: title?.trim() || "New conversation",
      created_at: new Date(0).toISOString(),
      updated_at: new Date(0).toISOString(),
      status: "active"
    };
    conversations = [conversation, ...conversations];
    transcripts.set(conversation.id, []);
    return { ...conversation };
  },

  async getConversation(id: string) {
    await delay(120);
    const conversation = conversations.find((c) => c.id === id);
    if (!conversation) throw new Error("Conversation not found.");
    return { ...conversation, messages: (transcripts.get(id) ?? []).map((m) => ({ ...m })) };
  },

  async setActiveFile(id: string, fileId: string) {
    await delay(100);
    const conversation = conversations.find((c) => c.id === id);
    const file = files.find((f) => f.id === fileId);
    if (!conversation) throw new Error("Conversation not found.");
    if (!file || file.status !== "ready") throw new Error("File not ready.");
    conversation.active_file_id = file.id;
    conversation.active_file_name = file.filename;
    touch(id);
    return {
      conversation_id: id,
      active_file_id: file.id,
      active_file_name: file.filename,
      status: file.status
    };
  },

  async renameConversation(id: string, title: string) {
    await delay(100);
    conversations = conversations.map((c) => (c.id === id ? { ...c, title } : c));
    const updated = conversations.find((c) => c.id === id);
    if (!updated) throw new Error("Conversation not found.");
    return { ...updated };
  },

  async deleteConversation(id: string) {
    await delay(100);
    conversations = conversations.filter((c) => c.id !== id);
    transcripts.delete(id);
  },

  async resetContext(id: string) {
    await delay(100);
    transcripts.set(id, []);
    return this.getConversation(id);
  },

  async sendMessage(id: string, message: string): Promise<ChatResponse> {
    await delay(650);
    const response = buildMockResponse(id, message);
    const turn = transcripts.get(id) ?? [];
    turn.push({ id: nextId("m"), role: "user", content: message });
    turn.push({
      id: response.message_id,
      role: "assistant",
      content: response.primary_value ?? response.summary ?? response.title,
      execution_mode: String(response.metadata.execution_mode ?? "")
    });
    transcripts.set(id, turn);
    // Auto-title from the first user message (mock parity with backend behaviour).
    const conversation = conversations.find((c) => c.id === id);
    if (conversation && (conversation.title === "New conversation") && turn.length === 2) {
      conversation.title = message.slice(0, 48);
    }
    touch(id);
    return response;
  },

  async listFiles() {
    await delay(120);
    return files.map((f) => ({ ...f }));
  },

  async uploadFile(file: File) {
    await delay(300);
    const record: UploadedFile = {
      id: nextId("file"),
      filename: file.name,
      size_bytes: file.size,
      status: "processing",
      uploaded_at: new Date(0).toISOString()
    };
    files = [...files, record];
    // Simulate ingestion finishing shortly after upload.
    setTimeout(() => {
      files = files.map((f) => (f.id === record.id ? { ...f, status: "ready" } : f));
    }, 1500);
    return { ...record };
  },

  async getFileStatus(fileId: string) {
    await delay(80);
    const file = files.find((f) => f.id === fileId);
    if (!file) throw new Error("File not found.");
    return { ...file };
  },

  async deleteFile(fileId: string) {
    await delay(100);
    files = files.filter((f) => f.id !== fileId);
  },

  artifactUrl(artifactId: string) {
    return `mock://artifacts/${encodeURIComponent(artifactId)}`;
  }
};
