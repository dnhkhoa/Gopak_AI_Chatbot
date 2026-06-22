import type { ChatResponse } from "../types/api";

export function DebugPanel({ response }: { response: ChatResponse }) {
  return (
    <details className="debug-panel">
      <summary>Debug</summary>
      <pre>{JSON.stringify(response.metadata, null, 2)}</pre>
    </details>
  );
}
