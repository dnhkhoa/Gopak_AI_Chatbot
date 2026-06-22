export type FileStatus = "uploaded" | "uploading" | "processing" | "ready" | "failed" | "deleting";

/** Shape returned by the (planned) /api/files endpoints. snake_case to match FastAPI. */
export interface UploadedFile {
  id: string;
  filename: string;
  size_bytes: number;
  status: FileStatus;
  error?: string | { code?: string; message?: string } | null;
  error_code?: string | null;
  error_message?: string | null;
  uploaded_at?: string | null;
  processing_stage?: string | null;
  progress?: number | null;
  queryable?: boolean | null;
  // Optional display-only metadata. Rendered in File details only when present;
  // the frontend never parses Excel to derive these (see API_INTEGRATION_REQUIREMENTS.md).
  row_count?: number | null;
  sheet_count?: number | null;
  table_count?: number | null;
  ready_at?: string | null;
  failed_at?: string | null;
}

export const ALLOWED_UPLOAD_EXTENSION = ".xlsx";
export const ALLOWED_UPLOAD_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export const UPLOAD_ACCEPT = `${ALLOWED_UPLOAD_EXTENSION},${ALLOWED_UPLOAD_MIME}`;

export function isXlsx(file: File): boolean {
  return file.name.toLowerCase().endsWith(ALLOWED_UPLOAD_EXTENSION);
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}
