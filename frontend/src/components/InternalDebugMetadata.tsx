import type { ChatResponse } from "../types/api";

type InternalMetadata = {
  execution_mode?: string;
  llm_called?: boolean;
  llm_model?: string | null;
  llm_latency_ms?: number | null;
  response_type?: string;
  active_file_name?: string | null;
};

function readInternal(response: ChatResponse): InternalMetadata | null {
  const value = response.metadata?.internal_debug_metadata;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as InternalMetadata;
}

function formatLatency(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return "";
  }
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
}

export function InternalDebugMetadata({ response }: { response: ChatResponse }) {
  const metadata = readInternal(response);
  if (!metadata) {
    return null;
  }
  const llm = metadata.llm_called
    ? `Yes${metadata.llm_model ? ` - ${metadata.llm_model}` : ""}${formatLatency(metadata.llm_latency_ms) ? ` - ${formatLatency(metadata.llm_latency_ms)}` : ""}`
    : "No";
  return (
    <details className="internal-debug-metadata">
      <summary>
        <span>Mode: {metadata.execution_mode ?? "UNKNOWN"}</span>
        <span>LLM: {llm}</span>
        <span>Response: {metadata.response_type ?? response.response_type}</span>
        {metadata.active_file_name ? <span>File: {metadata.active_file_name}</span> : null}
      </summary>
    </details>
  );
}
