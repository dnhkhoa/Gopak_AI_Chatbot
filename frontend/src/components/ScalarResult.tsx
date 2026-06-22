import type { ChatResponse } from "../types/api";

export function ScalarResult({ response }: { response: ChatResponse }) {
  return (
    <div className="scalar-result">
      <div className="eyebrow">{response.title}</div>
      <div className="scalar-value">{response.primary_value}</div>
      {response.summary ? <div className="muted">{response.summary}</div> : null}
    </div>
  );
}
