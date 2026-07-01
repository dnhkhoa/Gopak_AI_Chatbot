import { render, screen } from "@testing-library/react";
import { ReportPreview } from "./ReportPreview";
import type { ReportPayload } from "../types/api";

function report(overrides: Partial<ReportPayload> = {}): ReportPayload {
  return {
    report_id: "r-visual",
    root_report_id: "r-visual",
    parent_report_id: null,
    revision_number: 1,
    title: "Báo cáo trực quan",
    report_type: "production",
    audience: "management",
    detail_level: "STANDARD",
    target_page_range: "2-4",
    subtitle: "Phạm vi kiểm tra giao diện",
    source_file_name: "Production Analytics Bundle",
    date_range: { from: "2025-11-14", to: "2025-11-15" },
    generated_at: "09:00, ngày 27/06/2026",
    executive_summary: [],
    kpis: [],
    sections: [],
    source: { name: "Production Analytics Bundle", rows: 100 },
    filters: [],
    limitations: [],
    pdf_status: "ready",
    pdf_download_url: "/api/artifacts/report_visual.pdf/download",
    completeness: { purpose: "Kiểm tra trình bày báo cáo." },
    ...overrides
  };
}

const downloads = [{ id: "report_visual.pdf", label: "Tải báo cáo PDF", filename: "report_visual.pdf", mime_type: "application/pdf" }];

test("renders metadata-only report without empty sections", () => {
  render(<ReportPreview report={report()} downloads={downloads} />);
  expect(screen.getByAltText("i-Soft")).toBeInTheDocument();
  expect(screen.getByText("Báo cáo trực quan")).toBeInTheDocument();
  expect(screen.getByText("Kiểm tra trình bày báo cáo.")).toBeInTheDocument();
  expect(document.querySelectorAll("[data-section-type]").length).toBe(0);
});

test("renders KPI cards with stable labels and values", () => {
  render(<ReportPreview report={report({ kpis: [{ label: "Tổng downtime", value: "42,5", unit: "giờ", hint: "Theo payload." }] })} downloads={downloads} />);
  expect(screen.getByText("KPI tổng quan")).toBeInTheDocument();
  expect(screen.getByText("Tổng downtime")).toBeInTheDocument();
  expect(screen.getByText("42,5 giờ")).toBeInTheDocument();
});

test("renders report table and hides internal metadata columns", () => {
  render(
    <ReportPreview
      report={report({
        sections: [
          {
            section_type: "top_machines",
            title: "Top máy",
            summary: "Bảng máy theo downtime.",
            kpis: [],
            commentary: [],
            chart: null,
            table: {
              columns: ["machine", "downtime_hours", "source_id", "artifact_id"],
              rows: [{ machine: "Máy 11", downtime_hours: 42.5, source_id: "internal", artifact_id: "a1" }]
            }
          }
        ]
      })}
      downloads={downloads}
    />
  );
  expect(screen.getByText("Máy")).toBeInTheDocument();
  expect(screen.getByText("Downtime")).toBeInTheDocument();
  expect(screen.queryByText("source_id")).not.toBeInTheDocument();
  expect(screen.queryByText("artifact_id")).not.toBeInTheDocument();
});

test("renders chart section from report payload", () => {
  render(
    <ReportPreview
      report={report({
        sections: [
          {
            section_type: "trend",
            title: "Biểu đồ downtime",
            summary: "Xu hướng theo ngày.",
            kpis: [],
            commentary: [],
            table: null,
            chart: { type: "line", title: "Downtime theo ngày", x_key: "date_label", y_keys: ["downtime_hours"], y_axis_unit: "giờ", data: [{ date_label: "14/11", downtime_hours: 42.5 }] }
          }
        ]
      })}
      downloads={downloads}
    />
  );
  expect(screen.getByText("Downtime theo ngày")).toBeInTheDocument();
  expect(screen.getByText(/Trục X:/)).toBeInTheDocument();
});

test("renders full report with long commentary as separated bullets", () => {
  render(
    <ReportPreview
      report={report({
        executive_summary: ["Báo cáo có phần tóm tắt dài để kiểm tra khoảng trắng và ngắt dòng trong preview."],
        limitations: ["Giới hạn phân tích được lấy từ payload và hiển thị dưới dạng danh sách."],
        sections: [
          {
            section_type: "management",
            title: "Nhận xét quản lý",
            summary: "Các nhận xét được giữ theo thứ tự payload.",
            kpis: [],
            table: null,
            chart: null,
            commentary: [
              "Nhận xét thứ nhất được đặt trên một dòng riêng để dễ đọc.",
              "Nhận xét thứ hai vẫn giữ nguyên nội dung payload và không thêm dữ liệu mới."
            ]
          }
        ]
      })}
      downloads={downloads}
    />
  );
  expect(screen.getByText("Tóm tắt điều hành")).toBeInTheDocument();
  expect(screen.getByText("Nhận xét thứ nhất được đặt trên một dòng riêng để dễ đọc.")).toBeInTheDocument();
  expect(screen.getByText("Giới hạn phân tích")).toBeInTheDocument();
});

test("renders missing fields as unknown", () => {
  render(<ReportPreview report={report({ subtitle: "", generated_at: "", date_range: null, completeness: {} })} downloads={[]} />);
  expect(screen.getAllByText("Không xác định").length).toBeGreaterThanOrEqual(3);
  expect(screen.getByText("Đang tạo PDF")).toBeInTheDocument();
});
