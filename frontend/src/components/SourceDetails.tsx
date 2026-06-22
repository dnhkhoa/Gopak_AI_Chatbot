import type { ChatResponse } from "../types/api";

export function SourceDetails({ response }: { response: ChatResponse }) {
  if (!response.sources.length && !response.filters.length) {
    return null;
  }
  return (
    <details className="source-details">
      <summary>Nguồn và bộ lọc</summary>
      {response.sources.map((source) => (
        <div key={source.name} className="muted">
          {source.name}
          {source.rows != null ? ` · ${source.rows.toLocaleString("vi-VN")} dòng` : ""}
        </div>
      ))}
      {response.filters.map((filter, index) => (
        <div key={index} className="muted">
          {filter.label} {filter.operator} {String(filter.value ?? "")}
        </div>
      ))}
    </details>
  );
}
