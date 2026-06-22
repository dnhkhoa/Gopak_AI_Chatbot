import { request, uploadRequest } from "./http";
import type { UploadedFile } from "../types/files";

// NOTE: these endpoints are not yet implemented by the backend.
// See docs/API_INTEGRATION_REQUIREMENTS.md (BACKEND REQUIRED). In real mode they
// will 404 until the AI/Backend engineer adds them; use mock mode meanwhile.

export const listFiles = () => request<UploadedFile[]>("/files");

export const uploadFile = (file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return uploadRequest<UploadedFile>("/files/upload", formData);
};

export const getFileStatus = (fileId: string) =>
  request<UploadedFile>(`/files/${fileId}/status`);

export const deleteFile = (fileId: string) =>
  request<void>(`/files/${fileId}`, { method: "DELETE" });
