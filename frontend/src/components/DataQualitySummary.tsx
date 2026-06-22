import { DataTable } from "./DataTable";
import type { ChatResponse } from "../types/api";

export function DataQualitySummary({ response }: { response: ChatResponse }) {
  return (
    <div className="metadata-response">
      {response.title ? <h2>{response.title}</h2> : null}
      {response.summary ? <p>{response.summary}</p> : null}
      {response.table ? <DataTable table={response.table} /> : null}
    </div>
  );
}
