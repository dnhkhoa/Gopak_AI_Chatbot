import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { ChartPayload } from "../types/api";

const palette = ["#AEBCE8", "#C8DCC8", "#E8C6C6", "#D7C5E8", "#E8D8AE"];

export function ChartResult({ chart }: { chart: ChartPayload }) {
  if (!chart.data.length || !chart.y_keys.length) {
    return <div className="empty-inline">Không có dữ liệu biểu đồ.</div>;
  }
  const yKey = chart.y_keys[0];
  if (chart.type === "line") {
    return (
      <div className="chart-box">
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chart.data}>
            <CartesianGrid stroke="#E5E7EF" />
            <XAxis dataKey={chart.x_key} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Line type="monotone" dataKey={yKey} stroke="#AEBCE8" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (chart.type === "pie") {
    return (
      <div className="chart-box">
        <ResponsiveContainer width="100%" height={320}>
          <PieChart>
            <Tooltip />
            <Legend />
            <Pie data={chart.data} dataKey={yKey} nameKey={chart.x_key} innerRadius={72} outerRadius={118}>
              {chart.data.map((_, index) => (
                <Cell key={index} fill={palette[index % palette.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }
  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={chart.data} layout={chart.type === "horizontal_bar" ? "vertical" : "horizontal"}>
          <CartesianGrid stroke="#E5E7EF" />
          <XAxis dataKey={chart.type === "horizontal_bar" ? yKey : chart.x_key} type={chart.type === "horizontal_bar" ? "number" : "category"} tick={{ fontSize: 12 }} />
          <YAxis dataKey={chart.type === "horizontal_bar" ? chart.x_key : undefined} type={chart.type === "horizontal_bar" ? "category" : "number"} tick={{ fontSize: 12 }} width={120} />
          <Tooltip />
          <Bar dataKey={yKey} fill="#AEBCE8" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
