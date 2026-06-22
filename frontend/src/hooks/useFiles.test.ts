import { act, renderHook, waitFor } from "@testing-library/react";

vi.mock("../api/client", () => ({
  api: {
    listFiles: vi.fn().mockResolvedValue([]),
    uploadFile: vi.fn().mockResolvedValue({ id: "f9", filename: "ok.xlsx", size_bytes: 10, status: "processing" }),
    getFileStatus: vi.fn(),
    deleteFile: vi.fn().mockResolvedValue(undefined)
  }
}));

import { api } from "../api/client";
import { useFiles } from "./useFiles";

const xlsx = (name: string) =>
  new File([new Uint8Array(8)], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  });
const other = (name: string) => new File([new Uint8Array(8)], name, { type: "text/csv" });

test("rejects non-.xlsx files and does not upload them", async () => {
  const { result } = renderHook(() => useFiles());
  await waitFor(() => expect(result.current.loading).toBe(false));

  await act(async () => {
    await result.current.upload([other("data.csv")]);
  });

  expect(api.uploadFile).not.toHaveBeenCalled();
  expect(result.current.error).toBe("Only Excel .xlsx files are supported.");
});

test("uploads valid .xlsx files", async () => {
  const { result } = renderHook(() => useFiles());
  await waitFor(() => expect(result.current.loading).toBe(false));

  await act(async () => {
    await result.current.upload([xlsx("report.xlsx")]);
  });

  expect(api.uploadFile).toHaveBeenCalledTimes(1);
  expect(result.current.files.some((f) => f.filename === "ok.xlsx")).toBe(true);
});
