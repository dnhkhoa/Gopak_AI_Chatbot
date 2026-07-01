import { request } from "./http";
import type { ChatResponse } from "../types/api";

export const sendMessage = (id: string, message: string, debug = false, _sourceFileId?: string | null) =>
  request<ChatResponse>(`/conversations/${id}/messages`, {
    method: "POST",
    body: JSON.stringify({ message, debug })
  });
