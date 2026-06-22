import type {
  ActiveFilePayload,
  ChatResponse,
  ConversationDetail,
  ConversationPayload,
  HealthStatus
} from "../types/api";
import type { UploadedFile } from "../types/files";

/**
 * The single API contract shared by the real (FastAPI) and mock adapters.
 * UI components depend only on this interface, never on the transport.
 */
export interface GopakApi {
  health(): Promise<HealthStatus>;

  listConversations(): Promise<ConversationPayload[]>;
  createConversation(title?: string): Promise<ConversationPayload>;
  getConversation(id: string): Promise<ConversationDetail>;
  renameConversation(id: string, title: string): Promise<ConversationPayload>;
  deleteConversation(id: string): Promise<void>;
  resetContext(id: string): Promise<ConversationDetail>;
  setActiveFile(id: string, fileId: string): Promise<ActiveFilePayload>;

  sendMessage(id: string, message: string, debug?: boolean): Promise<ChatResponse>;

  listFiles(): Promise<UploadedFile[]>;
  uploadFile(file: File): Promise<UploadedFile>;
  getFileStatus(fileId: string): Promise<UploadedFile>;
  deleteFile(fileId: string): Promise<void>;

  artifactUrl(artifactId: string): string;
}
