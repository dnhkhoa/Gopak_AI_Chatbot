import { mockApi } from "../mocks/mockApi";
import { artifactUrl } from "./artifacts";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  resetContext,
  setActiveFile
} from "./conversations";
import type { GopakApi } from "./contract";
import { deleteFile, getFileStatus, listFiles, uploadFile } from "./files";
import { health } from "./health";
import { API_BASE_URL, API_MODE } from "./http";
import { sendMessage } from "./messages";

export { API_BASE_URL, API_MODE };

const realApi: GopakApi = {
  health,
  listConversations,
  createConversation,
  getConversation,
  renameConversation,
  deleteConversation,
  resetContext,
  setActiveFile,
  sendMessage,
  listFiles,
  uploadFile,
  getFileStatus,
  deleteFile,
  artifactUrl
};

// UI imports `api` only; the transport (real FastAPI vs in-browser mock) is
// chosen by VITE_API_MODE. Components are identical in both modes.
export const api: GopakApi = API_MODE === "mock" ? mockApi : realApi;
