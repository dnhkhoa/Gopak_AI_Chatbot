import type { ChatResponse } from "../types/api";
import { DataTable } from "./DataTable";
import { NarrativeBlock } from "./NarrativeBlock";
import { isRenderableNarrative } from "./narrative";

export function AnalysisResponse({ response }: { response: ChatResponse }) {
  const analysis = response.analysis;
  const summary = analysis?.summary ?? response.summary;
  const insights = analysis?.insights ?? [];
  const table = analysis?.table ?? response.table;

  return (
    <div className="analysis-response">
      {isRenderableNarrative(analysis?.headline ?? response.title) ? <h2>{analysis?.headline ?? response.title}</h2> : null}
      {isRenderableNarrative(summary) ? <NarrativeBlock text={summary} /> : null}
      {insights.length ? (
        <div className="insight-list">
          {insights.filter((item) => isRenderableNarrative(item.text)).map((item, index) => (
            <div className="insight-card" key={`${item.text}-${index}`}>
              <p>{item.text}</p>
              {item.evidence.length ? <span>{item.evidence.slice(0, 3).join(" · ")}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
      {table ? <DataTable table={table} /> : null}
    </div>
  );
}
