import { ChartResult } from "./ChartResult";
import { ClarificationMessage } from "./ClarificationMessage";
import { DashboardResult } from "./DashboardResult";
import { DataOverviewMessage } from "./DataOverviewMessage";
import { DataQualitySummary } from "./DataQualitySummary";
import { DataTable } from "./DataTable";
import { DebugPanel } from "./DebugPanel";
import { DownloadActions } from "./DownloadActions";
import { ErrorMessage } from "./ErrorMessage";
import { RefusalMessage } from "./RefusalMessage";
import { ScalarResult } from "./ScalarResult";
import { SampleRowsTable } from "./SampleRowsTable";
import { SchemaTable } from "./SchemaTable";
import { SourceDetails } from "./SourceDetails";
import { Sparkles } from "lucide-react";
import type { UiMessage } from "../types/api";

function AssistantAvatar() {
  return (
    <div className="assistant-avatar" aria-hidden="true">
      <Sparkles size={16} />
    </div>
  );
}

export function ChatMessage({ message, debug }: { message: UiMessage; debug: boolean }) {
  if (message.role === "user") {
    return <div className="message-row user"><div className="bubble">{message.content}</div></div>;
  }
  const response = message.response;
  if (!response) {
    return (
      <div className="message-row assistant">
        <AssistantAvatar />
        <div className="assistant-content">{message.content}</div>
      </div>
    );
  }
  return (
    <div className="message-row assistant">
      <AssistantAvatar />
      <div className="assistant-content">
        {response.response_type === "scalar" ? <ScalarResult response={response} /> : null}
        {response.response_type === "clarification" ? <ClarificationMessage text={response.summary} /> : null}
        {response.response_type === "refusal" ? <RefusalMessage text={response.summary} /> : null}
        {response.response_type === "error" ? <ErrorMessage text={response.summary} /> : null}
        {response.response_type === "data_overview" ? <DataOverviewMessage response={response} /> : null}
        {response.response_type === "schema" ? <SchemaTable response={response} /> : null}
        {response.response_type === "sample_table" ? <SampleRowsTable response={response} /> : null}
        {response.response_type === "data_quality" ? <DataQualitySummary response={response} /> : null}
        {!["scalar", "clarification", "refusal", "error", "data_overview", "schema", "sample_table", "data_quality"].includes(response.response_type) ? (
          <>
            {response.title ? <h2>{response.title}</h2> : null}
            {response.summary ? <p>{response.summary}</p> : null}
          </>
        ) : null}
        {response.chart ? <ChartResult chart={response.chart} /> : null}
        {response.dashboard ? <DashboardResult dashboard={response.dashboard} /> : null}
        {response.table && !["data_overview", "schema", "sample_table", "data_quality"].includes(response.response_type) ? <DataTable table={response.table} /> : null}
        <DownloadActions downloads={response.downloads} />
        <SourceDetails response={response} />
        {debug ? <DebugPanel response={response} /> : null}
      </div>
    </div>
  );
}
