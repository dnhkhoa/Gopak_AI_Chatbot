import { AnalysisResponse } from "./AnalysisResponse";
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
import { ReportPreview } from "./ReportPreview";
import { ScalarResult } from "./ScalarResult";
import { SampleRowsTable } from "./SampleRowsTable";
import { SchemaTable } from "./SchemaTable";
import { SourceDetails } from "./SourceDetails";
import { InternalDebugMetadata } from "./InternalDebugMetadata";
import { isRenderableNarrative } from "./narrative";
import { Sparkles } from "lucide-react";
import type { ChatResponse, UiMessage } from "../types/api";

function AssistantAvatar() {
  return (
    <div className="assistant-avatar" aria-hidden="true">
      <Sparkles size={16} />
    </div>
  );
}

export function ChatMessage({ message, debug, internalDebug = false }: { message: UiMessage; debug: boolean; internalDebug?: boolean }) {
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
        <ResponseBody response={response} />
        <DownloadActions downloads={response.downloads} />
        <SourceDetails response={response} />
        {internalDebug ? <InternalDebugMetadata response={response} /> : null}
        {debug ? <DebugPanel response={response} /> : null}
      </div>
    </div>
  );
}

function ResponseBody({ response }: { response: ChatResponse }) {
  switch (response.response_type) {
    case "report":
      return response.report ? <ReportPreview report={response.report} downloads={response.downloads} /> : <FallbackText response={response} />;
    case "chart":
      return (
        <>
          <FallbackText response={response} />
          {response.chart ? <ChartResult chart={response.chart} /> : null}
          {response.table ? <DataTable table={response.table} /> : null}
        </>
      );
    case "analysis":
      return <AnalysisResponse response={response} />;
    case "table":
      return (
        <>
          <FallbackText response={response} />
          {response.table ? <DataTable table={response.table} /> : null}
        </>
      );
    case "dashboard":
      return (
        <>
          <FallbackText response={response} />
          {response.dashboard ? <DashboardResult dashboard={response.dashboard} /> : null}
        </>
      );
    case "scalar":
      return <ScalarResult response={response} />;
    case "clarification":
      return <ClarificationMessage text={isRenderableNarrative(response.summary) ? response.summary : ""} />;
    case "refusal":
      return <RefusalMessage text={isRenderableNarrative(response.summary) ? response.summary : ""} />;
    case "error":
      return <ErrorMessage text={isRenderableNarrative(response.summary) ? response.summary : ""} />;
    case "data_overview":
      return <DataOverviewMessage response={response} />;
    case "schema":
      return <SchemaTable response={response} />;
    case "sample_table":
      return <SampleRowsTable response={response} />;
    case "data_quality":
      return <DataQualitySummary response={response} />;
    default:
      return <FallbackText response={response} />;
  }
}

function FallbackText({ response }: { response: ChatResponse }) {
  return (
    <>
      {response.title?.trim() ? <h2>{response.title}</h2> : null}
      {isRenderableNarrative(response.summary) ? <p>{response.summary}</p> : null}
    </>
  );
}
