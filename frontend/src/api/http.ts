export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

/** "mock" uses in-browser fixtures; "real" calls the FastAPI backend. */
export const API_MODE: "real" | "mock" =
  import.meta.env.VITE_API_MODE === "mock" ? "mock" : "real";

const GENERIC_ERROR = "Unable to reach the analysis service.";

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    }
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? GENERIC_ERROR);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

/** Multipart upload (no JSON content-type so the browser sets the boundary). */
export async function uploadRequest<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: formData });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? GENERIC_ERROR);
  }
  return response.json() as Promise<T>;
}
