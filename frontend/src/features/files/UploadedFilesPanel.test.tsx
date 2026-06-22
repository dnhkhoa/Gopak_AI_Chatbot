import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadedFilesPanel } from "./UploadedFilesPanel";
import type { UseFiles } from "../../hooks/useFiles";
import type { UploadedFile } from "../../types/files";

const longName = "Machine_Downtime_a_very_long_filename_that_should_truncate_2026.xlsx";

const files: UploadedFile[] = [
  { id: "f1", filename: longName, size_bytes: 2_516_582, status: "ready" },
  { id: "f2", filename: "Loss.xlsx", size_bytes: 1_048_576, status: "processing" }
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

test("renders the uploaded files panel with status, totals and ellipsis title", () => {
  render(<UploadedFilesPanel files={makeUseFiles()} />);
  expect(screen.getByText("Uploaded files")).toBeInTheDocument();
  expect(screen.getByText("Ready")).toBeInTheDocument();
  expect(screen.getByText("Processing")).toBeInTheDocument();
  // Long filename is present with a tooltip (title attribute) for the full name.
  expect(screen.getByTitle(longName)).toBeInTheDocument();
  expect(screen.getByText("2 files uploaded")).toBeInTheDocument();
});

test("remove calls the handler (no confirm for non-ready files)", async () => {
  const remove = vi.fn();
  render(<UploadedFilesPanel files={makeUseFiles({ remove })} />);
  await userEvent.click(screen.getByLabelText("Remove Loss.xlsx"));
  expect(remove).toHaveBeenCalledWith("f2");
});

test("shows a friendly error with retry", () => {
  render(<UploadedFilesPanel files={makeUseFiles({ error: "Only Excel .xlsx files are supported." })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Only Excel .xlsx files are supported.");
  expect(screen.getByLabelText("Retry upload")).toBeInTheDocument();
});
