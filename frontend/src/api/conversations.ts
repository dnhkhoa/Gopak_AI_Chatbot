import { request } from "./http";
import type { ActiveFilePayload, ConversationDetail, ConversationPayload } from "../types/api";

export const listConversations = () => request<ConversationPayload[]>("/conversations");

export const createConversation = (title?: string, sourceFileId?: string) =>
  request<ConversationPayload>("/conversations", {
    method: "POST",
    body: JSON.stringify({ title, source_file_id: sourceFileId })
  });

export const getConversation = (id: string) =>
  request<ConversationDetail>(`/conversations/${id}`);

export const renameConversation = (id: string, title: string) =>
  request<ConversationPayload>(`/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title })
  });

export const deleteConversation = (id: string) =>
  request<void>(`/conversations/${id}`, { method: "DELETE" });

export const resetContext = (id: string) =>
  request<ConversationDetail>(`/conversations/${id}/reset-context`, { method: "POST" });

export const setActiveFile = (id: string, fileId: string) =>
  request<ActiveFilePayload>(`/conversations/${id}/active-file`, {
    method: "PUT",
    body: JSON.stringify({ file_id: fileId })
  });
