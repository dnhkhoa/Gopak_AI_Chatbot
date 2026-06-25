import { Download, FileText } from "lucide-react";
import type { DownloadPayload, ReportPayload } from "../types/api";
import { ChartResult } from "./ChartResult";
import { DataTable } from "./DataTable";
import { isRenderableNarrative } from "./narrative";

export function ReportPreview({ report, downloads }: { report: ReportPayload; downloads: DownloadPayload[] }) {
  const pdfDownload = downloads.find((item) => item.mime_type === "application/pdf" || item.filename.toLowerCase().endsWith(".pdf"));
  const sourceName = report.source_file_name || report.source.name;

  return (
    <section className="report-preview" data-testid="report-preview">
      <header className="report-preview-header">
        <div>
          <span className="report-eyebrow"><FileText size={14} /> Báo cáo</span>
          <h2>{report.title}</h2>
          {report.subtitle ? <p>{report.subtitle}</p> : null}
          <small>{[sourceName, report.generated_at].filter(Boolean).join(" · ")}</small>
        </div>
        <div className="report-actions">
          {pdfDownload ? (
            <DownloadLink download={pdfDownload} label="Tải báo cáo PDF" />
          ) : (
            <span className="report-status">{report.pdf_status === "failed" ? "PDF chưa sẵn sàng" : "Đang tạo PDF"}</span>
          )}
        </div>
      </header>

      {report.executive_summary.length ? (
        <div className="report-section">
          <h3>Tóm tắt điều hành</h3>
          <ul>
            {report.executive_summary.filter(isRenderableNarrative).map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </div>
      ) : null}

      {report.kpis.length ? (
        <div className="kpi-grid">
          {report.kpis.map((kpi) => (
            <div className="kpi-card" key={kpi.label}>
              <span>{kpi.label}</span>
              <strong>{[kpi.value, kpi.unit].filter(Boolean).join(" ")}</strong>
              {isRenderableNarrative(kpi.hint) ? <small>{kpi.hint}</small> : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="report-sections" data-testid="report-sections">
        {report.sections.map((section) => (
          <article className="report-section" data-section-type={section.section_type} key={section.section_type}>
            <header>
              <h3>{section.title}</h3>
              <span>{section.table ? "Bảng" : section.chart ? "Biểu đồ" : section.kpis.length ? "KPI" : "Nhận xét"}</span>
            </header>
            {isRenderableNarrative(section.summary) ? <p>{section.summary}</p> : null}
            {section.kpis.length ? (
              <div className="mini-kpis">
                {section.kpis.map((kpi) => <span key={kpi.label}>{kpi.label}: <strong>{[kpi.value, kpi.unit].filter(Boolean).join(" ")}</strong></span>)}
              </div>
            ) : null}
            {section.chart ? <ChartResult chart={section.chart} /> : null}
            {section.table ? <DataTable table={{ columns: section.table.columns, rows: section.table.rows.slice(0, 8) }} /> : null}
            {section.commentary.filter(isRenderableNarrative).map((item, index) => <p className="report-commentary" key={index}>{item}</p>)}
          </article>
        ))}
      </div>

      <footer className="report-section">
        <h3>Nguồn và giới hạn</h3>
        <p>{sourceName}{report.source.rows ? ` · ${report.source.rows.toLocaleString("vi-VN")} dòng` : ""}</p>
        {report.limitations.filter(isRenderableNarrative).map((item, index) => <p className="report-commentary" key={index}>{item}</p>)}
      </footer>
    </section>
  );
}

function DownloadLink({ download, label }: { download: DownloadPayload; label: string }) {
  return (
    <a className="download-chip" href={`/api/artifacts/${download.id}/download`}>
      <Download size={14} />
      {label}
    </a>
  );
}
