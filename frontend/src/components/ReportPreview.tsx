import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { ReactNode } from "react";
import { api } from "../api/client";
import logoUrl from "../assets/isoft-logo.png";
import type { ChartPayload, DownloadPayload, KpiCard, PublicReportSection, ReportPayload, TablePayload } from "../types/api";
import { isRenderableNarrative } from "./narrative";
import styles from "./ReportPreview.module.css";

const UNKNOWN = "Không xác định";
const INTERNAL_COLUMNS = new Set([
  "source_id",
  "artifact_id",
  "query_result_id",
  "query_plan_id",
  "schema_version",
  "canonical_metric_key",
  "canonical metric key",
  "result_id"
]);
const COLUMN_LABELS: Record<string, string> = {
  metric: "Chỉ số",
  value: "Giá trị",
  unit: "Đơn vị",
  time_scope: "Phạm vi",
  snapshot_time: "Thời điểm",
  source: "Nguồn",
  machine: "Máy",
  downtime_hours: "Downtime",
  event_count: "Số lần",
  loss_group: "Nhóm tổn thất",
  date_label: "Ngày"
};

export function ReportPreview({ report, downloads }: { report: ReportPayload; downloads: DownloadPayload[] }) {
  const pdfDownload = downloads.find((item) => item.mime_type === "application/pdf" || item.filename.toLowerCase().endsWith(".pdf"));
  const revisionNumber = report.revision_number ?? 1;
  const sourceName = displayValue(report.source_file_name || report.source?.name);
  const reportSections = report.sections.filter((section) => hasSectionContent(section) && !isSourceLimitSection(section));
  const metadata = [
    ["File nguồn", sourceName],
    ["Phạm vi dữ liệu", dateRangeText(report.date_range)],
    ["Thời gian tạo", displayValue(report.generated_at)],
    ["Mục tiêu", reportPurpose(report)]
  ];

  return (
    <section className={styles.shell} data-testid="report-preview">
      <article className={styles.page}>
        <header className={styles.header}>
          <div className={styles.logoBlock}>
            <img src={logoUrl} alt="i-Soft" className={styles.logo} />
          </div>
          <div className={styles.titleBlock}>
            <div className={styles.version}>Phiên bản {revisionNumber}</div>
            <h2>{displayValue(report.title)}</h2>
          </div>
        </header>

        <div className={styles.rule} />

        <section className={styles.cover}>
          <p className={styles.subtitle}>{displayValue(report.subtitle)}</p>
          <dl className={styles.metadata}>
            {metadata.map(([label, value]) => (
              <div className={styles.metadataRow} key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <div className={styles.actions}>
            {pdfDownload ? (
              <a className={styles.downloadButton} href={api.artifactUrl(pdfDownload.id)}>
                Tải báo cáo PDF
              </a>
            ) : (
              <span className={styles.status}>{report.pdf_status === "failed" ? "PDF chưa sẵn sàng" : "Đang tạo PDF"}</span>
            )}
          </div>
        </section>

        {report.executive_summary.filter(isRenderableNarrative).length ? (
          <ReportSection title="Tóm tắt điều hành">
            <ul className={styles.bulletList}>
              {report.executive_summary.filter(isRenderableNarrative).map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </ReportSection>
        ) : null}

        {report.kpis.length ? (
          <ReportSection title="KPI tổng quan">
            <div className={styles.kpiGrid}>
              {report.kpis.map((kpi) => (
                <KpiCardView kpi={kpi} key={`${kpi.label}-${kpi.value}`} />
              ))}
            </div>
          </ReportSection>
        ) : null}

        <div className={styles.sections} data-testid="report-sections">
          {reportSections.map((section) => (
            <ReportSection title={displayValue(section.title)} key={section.section_type} sectionType={section.section_type}>
              <ReportSectionBody section={section} />
            </ReportSection>
          ))}
        </div>

        <ReportSourceFooter report={report} sourceName={sourceName} />
      </article>
    </section>
  );
}

function ReportSection({ title, children, sectionType }: { title: string; children: ReactNode; sectionType?: string }) {
  return (
    <section className={styles.section} data-section-type={sectionType}>
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function ReportSectionBody({ section }: { section: PublicReportSection }) {
  const commentary = section.commentary.filter(isRenderableNarrative);
  return (
    <>
      {isRenderableNarrative(section.summary) ? <p className={styles.paragraph}>{section.summary}</p> : null}
      {section.kpis.length ? (
        <div className={styles.miniKpis}>
          {section.kpis.map((kpi) => (
            <KpiCardView kpi={kpi} compact key={`${kpi.label}-${kpi.value}`} />
          ))}
        </div>
      ) : null}
      {commentary.length ? (
        <ul className={styles.bulletList}>
          {commentary.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : null}
      {section.chart && hasChartData(section.chart) ? <ReportChart chart={section.chart} /> : null}
      {section.table && section.table.rows.length ? <ReportTable table={section.table} /> : null}
    </>
  );
}

function KpiCardView({ kpi, compact = false }: { kpi: KpiCard; compact?: boolean }) {
  return (
    <div className={compact ? styles.kpiCardCompact : styles.kpiCard}>
      <span>{displayValue(kpi.label)}</span>
      <strong>{[kpi.value, kpi.unit].filter(Boolean).join(" ") || UNKNOWN}</strong>
      {isRenderableNarrative(kpi.hint) ? <small>{kpi.hint}</small> : null}
    </div>
  );
}

function ReportTable({ table }: { table: TablePayload }) {
  const columns = publicColumns(table);
  if (!columns.length || !table.rows.length) return null;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{columnLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.slice(0, 12).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td className={looksNumeric(row[column]) ? styles.numeric : undefined} key={column}>
                  {displayValue(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportChart({ chart }: { chart: ChartPayload }) {
  const yKey = chart.y_keys[0];
  const unit = chart.y_axis_unit || chart.tooltip_unit || "";
  const tooltip = (value: unknown) => [`${value}${unit ? ` ${unit}` : ""}`, columnLabel(yKey)];
  return (
    <div className={styles.chartBox}>
      <div className={styles.chartTitle}>{displayValue(chart.title)}</div>
      <ResponsiveContainer width="100%" height={280}>
        {chart.type === "line" ? (
          <LineChart data={chart.data} margin={{ top: 12, right: 18, bottom: 20, left: 4 }}>
            <CartesianGrid stroke="#D9E2EC" />
            <XAxis dataKey={chart.x_key} tick={{ fontSize: 11, fill: "#64748B" }} />
            <YAxis tick={{ fontSize: 11, fill: "#64748B" }} />
            <Tooltip formatter={tooltip} />
            <Line type="monotone" dataKey={yKey} stroke="#2F66A8" strokeWidth={2.2} dot={false} />
          </LineChart>
        ) : chart.type === "pie" ? (
          <PieChart margin={{ top: 12, right: 18, bottom: 20, left: 18 }}>
            <Tooltip formatter={tooltip} />
            <Pie data={chart.data} dataKey={yKey} nameKey={chart.x_key} innerRadius={58} outerRadius={96}>
              {chart.data.map((_, index) => (
                <Cell key={index} fill={index % 2 === 0 ? "#2F66A8" : "#173B6C"} />
              ))}
            </Pie>
          </PieChart>
        ) : (
          <BarChart data={chart.data} layout={chart.type === "horizontal_bar" ? "vertical" : "horizontal"} margin={{ top: 12, right: 18, bottom: 20, left: 4 }}>
            <CartesianGrid stroke="#D9E2EC" />
            <XAxis dataKey={chart.type === "horizontal_bar" ? yKey : chart.x_key} type={chart.type === "horizontal_bar" ? "number" : "category"} tick={{ fontSize: 11, fill: "#64748B" }} />
            <YAxis dataKey={chart.type === "horizontal_bar" ? chart.x_key : undefined} type={chart.type === "horizontal_bar" ? "category" : "number"} tick={{ fontSize: 11, fill: "#64748B" }} width={112} />
            <Tooltip formatter={tooltip} />
            <Bar dataKey={yKey} fill="#2F66A8" radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
      <div className={styles.axisNote}>
        Trục X: {displayValue(chart.x_key)}{yKey ? ` · Trục Y: ${columnLabel(yKey)}${unit ? ` (${unit})` : ""}` : ""}
      </div>
    </div>
  );
}

function ReportSourceFooter({ report, sourceName }: { report: ReportPayload; sourceName: string }) {
  const filters = report.filters.filter((item) => Object.keys(item).length);
  return (
    <footer className={styles.footer}>
      <h3>{report.limitations.length ? "Nguồn dữ liệu và giới hạn phân tích" : "Nguồn dữ liệu và bộ lọc"}</h3>
      <dl className={styles.metadata}>
        <div className={styles.metadataRow}>
          <dt>Nguồn dữ liệu</dt>
          <dd>{report.source.rows ? `${sourceName} · ${report.source.rows.toLocaleString("vi-VN")} dòng` : sourceName}</dd>
        </div>
        <div className={styles.metadataRow}>
          <dt>Phạm vi</dt>
          <dd>{dateRangeText(report.date_range)}</dd>
        </div>
        <div className={styles.metadataRow}>
          <dt>Bộ lọc</dt>
          <dd>{filters.length ? filters.map(filterText).join("; ") : UNKNOWN}</dd>
        </div>
      </dl>
      {report.limitations.filter(isRenderableNarrative).length ? (
        <div className={styles.limitations}>
          <h4>Giới hạn phân tích</h4>
          <ul className={styles.bulletList}>
            {report.limitations.filter(isRenderableNarrative).map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </footer>
  );
}

function hasSectionContent(section: PublicReportSection): boolean {
  return Boolean(
    section.title?.trim() &&
      (isRenderableNarrative(section.summary) ||
        section.kpis.length ||
        section.commentary.some(isRenderableNarrative) ||
        (section.table?.rows.length ?? 0) > 0 ||
        hasChartData(section.chart))
  );
}

function isSourceLimitSection(section: PublicReportSection): boolean {
  const key = `${section.section_type} ${section.title}`.toLowerCase();
  return (key.includes("nguồn") && key.includes("giới hạn")) || (key.includes("source") && key.includes("limit"));
}

function hasChartData(chart?: ChartPayload | null): chart is ChartPayload {
  return Boolean(chart && chart.data.length && chart.y_keys.length);
}

function publicColumns(table: TablePayload): string[] {
  return table.columns.filter((column) => !INTERNAL_COLUMNS.has(column.toLowerCase())).slice(0, 6);
}

function columnLabel(column: string): string {
  const key = column.toLowerCase();
  return COLUMN_LABELS[key] ?? column.replace(/_/g, " ");
}

function reportPurpose(report: ReportPayload): string {
  const value = report.completeness?.purpose ?? report.completeness?.objective ?? report.completeness?.layout_config;
  if (typeof value === "string" && value.trim()) return value.trim();
  if (value && typeof value === "object" && "purpose" in value && typeof value.purpose === "string") return value.purpose;
  return UNKNOWN;
}

function dateRangeText(range?: Record<string, unknown> | null): string {
  if (!range) return UNKNOWN;
  const start = range.from ?? range.start;
  const end = range.to ?? range.end;
  if (!start && !end) return UNKNOWN;
  return [start, end].map(formatDate).filter(Boolean).join(" - ") || UNKNOWN;
}

function formatDate(value: unknown): string {
  if (!value) return "";
  const text = String(value);
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : text;
}

function filterText(filter: Record<string, unknown>): string {
  const label = displayValue(filter.label);
  const operator = displayValue(filter.operator);
  const value = displayValue(filter.value);
  return [label, operator, value].filter((item) => item !== UNKNOWN).join(" ") || UNKNOWN;
}

function looksNumeric(value: unknown): boolean {
  return typeof value === "number" || (/^-?\d+([.,]\d+)?$/u.test(String(value).trim()) && String(value).trim().length > 0);
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return UNKNOWN;
  if (typeof value === "number") return Number.isFinite(value) ? value.toLocaleString("vi-VN") : UNKNOWN;
  return String(value).trim() || UNKNOWN;
}
