import type { TablePayload } from "../types/api";

export function DataTable({ table }: { table: TablePayload }) {
  if (!table.rows.length) {
    return <div className="empty-inline">Không có dữ liệu.</div>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={index}>
              {table.columns.map((column) => (
                <td key={column}>{String(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
