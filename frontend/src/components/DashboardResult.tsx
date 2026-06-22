import { ChartResult } from "./ChartResult";
import { DataTable } from "./DataTable";
import type { DashboardPayload } from "../types/api";

export function DashboardResult({ dashboard }: { dashboard: DashboardPayload }) {
  return (
    <div className="dashboard-result">
      <div className="kpi-grid">
        {dashboard.cards.map((card, index) => (
          <div className="kpi-card" key={index}>
            <div className="eyebrow">{String(card.label ?? "")}</div>
            <div className="kpi-value">{String(card.value ?? "")}</div>
          </div>
        ))}
      </div>
      {dashboard.chart ? <ChartResult chart={dashboard.chart} /> : null}
      {dashboard.table ? <DataTable table={dashboard.table} /> : null}
    </div>
  );
}
