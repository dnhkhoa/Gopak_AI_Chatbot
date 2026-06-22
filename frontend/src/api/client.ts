import type { ChatResponse, ConversationDetail, ConversationPayload, HealthStatus } from "../types/api";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    }
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Không thể kết nối với hệ thống xử lý.");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthStatus>("/health"),
  listConversations: () => request<ConversationPayload[]>("/conversations"),
  createConversation: (title?: string) =>
    request<ConversationPayload>("/conversations", {
      method: "POST",
      body: JSON.stringify({ title })
    }),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<ConversationPayload>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title })
    }),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, {
      method: "DELETE"
    }),
  resetContext: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}/reset-context`, {
      method: "POST"
    }),
  sendMessage: (id: string, message: string, debug: boolean) =>
    request<ChatResponse>(`/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ message, debug })
    }),
  artifactUrl: (id: string) => `${API_BASE_URL}/artifacts/${encodeURIComponent(id)}/download`
};
