import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadedFilesPanel } from "./UploadedFilesPanel";
import type { UseFiles } from "../../hooks/useFiles";
import type { UploadedFile } from "../../types/files";

const longName = "Machine_Downtime_a_very_long_filename_that_should_truncate_2026.xlsx";

const files: UploadedFile[] = [
  { id: "f1", filename: longName, size_bytes: 2_516_582, status: "ready", uploaded_at: "2026-06-20T00:00:00Z", row_count: 9151, sheet_count: 1 },
  { id: "f2", filename: "Loss.xlsx", size_bytes: 1_048_576, status: "processing" },
  { id: "f3", filename: "Broken.xlsx", size_bytes: 512, status: "failed", error: "Header detection failed" }
];

function makeUseFiles(overrides: Partial<UseFiles> = {}): UseFiles {
  return {
    files,
    loading: false,
    error: null,
    upload: vi.fn(),
    remove: vi.fn(),
    retry: vi.fn(),
    refresh: vi.fn(),
    clearError: vi.fn(),
    ...overrides
  };
}

const item = (name: RegExp) => screen.getByRole("button", { name });

test("renders an Excel icon, totals and status for every file (not hardcoded)", () => {
  const { container } = render(<UploadedFilesPanel files={makeUseFiles()} />);
  expect(container.querySelectorAll(".file-icon")).toHaveLength(3);
  expect(screen.getByText("Ready")).toBeInTheDocument();
  expect(screen.getByText("Processing")).toBeInTheDocument();
  expect(screen.getByText("Failed")).toBeInTheDocument();
  expect(screen.getByText("3 files uploaded")).toBeInTheDocument();
});

test("long filename is truncated via CSS but exposed through a tooltip title", () => {
  render(<UploadedFilesPanel files={makeUseFiles()} />);
  expect(screen.getByTitle(longName)).toBeInTheDocument();
});

test("clicking selects a file, and clicking another moves the selection", async () => {
  render(<UploadedFilesPanel files={makeUseFiles()} />);
  await userEvent.click(item(/^Loss\.xlsx,/));
  expect(item(/^Loss\.xlsx,/)).toHaveAttribute("aria-selected", "true");

  await userEvent.click(item(/^Broken\.xlsx,/));
  expect(item(/^Broken\.xlsx,/)).toHaveAttribute("aria-selected", "true");
  expect(item(/^Loss\.xlsx,/)).toHaveAttribute("aria-selected", "false");
});

test("Enter opens the file details popover with real metadata only", async () => {
  render(<UploadedFilesPanel files={makeUseFiles()} />);
  item(/^Machine_Downtime/).focus();
  await userEvent.keyboard("{Enter}");
  const dialog = screen.getByRole("dialog", { name: /Details for/ });
  expect(within(dialog).getByText("Rows")).toBeInTheDocument();
  expect(within(dialog).getByText("9,151")).toBeInTheDocument();
  expect(within(dialog).getByText("Sheets")).toBeInTheDocument();
});

test("the three-dot menu removes a file via the API after confirmation", async () => {
  const remove = vi.fn();
  const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<UploadedFilesPanel files={makeUseFiles({ remove })} />);

  await userEvent.click(screen.getByRole("button", { name: `Options for ${longName}` }));
  await userEvent.click(screen.getByRole("menuitem", { name: /Remove file/ }));

  expect(confirmSpy).toHaveBeenCalled();
  expect(remove).toHaveBeenCalledWith("f1");
  confirmSpy.mockRestore();
});

test("remove is cancelled when the user declines confirmation", async () => {
  const remove = vi.fn();
  const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<UploadedFilesPanel files={makeUseFiles({ remove })} />);

  await userEvent.click(screen.getByRole("button", { name: `Options for ${longName}` }));
  await userEvent.click(screen.getByRole("menuitem", { name: /Remove file/ }));

  expect(remove).not.toHaveBeenCalled();
  confirmSpy.mockRestore();
});

test("shows a friendly upload error with retry", () => {
  render(<UploadedFilesPanel files={makeUseFiles({ error: "Only Excel .xlsx files are supported." })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Only Excel .xlsx files are supported.");
  expect(screen.getByLabelText("Retry upload")).toBeInTheDocument();
});
