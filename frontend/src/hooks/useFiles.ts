import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { isXlsx, type UploadedFile } from "../types/files";

const POLL_MS = 1200;

export interface UseFiles {
  files: UploadedFile[];
  loading: boolean;
  error: string | null;
  upload: (fileList: FileList | File[]) => Promise<void>;
  remove: (fileId: string) => Promise<void>;
  retry: () => Promise<void>;
  refresh: () => Promise<void>;
  clearError: () => void;
}

export function useFiles(): UseFiles {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastUpload = useRef<File | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setFiles(await api.listFiles());
    } catch {
      setError("Couldn't load uploaded files.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while any file is still uploading/processing.
  useEffect(() => {
    const pending = files.filter((f) => f.status === "uploading" || f.status === "processing");
    if (!pending.length) return;
    const timer = setTimeout(async () => {
      try {
        const updated = await Promise.all(pending.map((f) => api.getFileStatus(f.id)));
        setFiles((current) => current.map((f) => updated.find((u) => u.id === f.id) ?? f));
      } catch {
        /* transient; next tick retries */
      }
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [files]);

  const upload = useCallback(async (fileList: FileList | File[]) => {
    const incoming = Array.from(fileList);
    const valid = incoming.filter(isXlsx);
    if (valid.length !== incoming.length) {
      setError("Only Excel .xlsx files are supported.");
    }
    for (const file of valid) {
      if (files.some((f) => f.filename === file.name && f.status !== "failed")) {
        setError(`"${file.name}" is already uploaded.`);
        continue;
      }
      lastUpload.current = file;
      try {
        const created = await api.uploadFile(file);
        setFiles((current) => [...current, created]);
      } catch {
        setError(`Upload failed for "${file.name}".`);
      }
    }
  }, [files]);

  const remove = useCallback(async (fileId: string) => {
    try {
      await api.deleteFile(fileId);
      setFiles((current) => current.filter((f) => f.id !== fileId));
    } catch {
      setError("Couldn't remove the file.");
    }
  }, []);

  const retry = useCallback(async () => {
    if (lastUpload.current) await upload([lastUpload.current]);
  }, [upload]);

  return { files, loading, error, upload, remove, retry, refresh, clearError: () => setError(null) };
}
