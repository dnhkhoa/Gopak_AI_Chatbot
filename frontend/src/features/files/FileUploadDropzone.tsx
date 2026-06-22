import { FileSpreadsheet, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { ALLOWED_UPLOAD_MIME, UPLOAD_ACCEPT } from "../../types/files";

type DragState = "idle" | "valid" | "invalid";

function dragKind(dataTransfer: DataTransfer): DragState {
  const items = Array.from(dataTransfer.items ?? []);
  if (!items.length) return "valid"; // type often unavailable mid-drag; assume valid
  const allXlsx = items.every((item) => item.kind !== "file" || item.type === ALLOWED_UPLOAD_MIME || item.type === "");
  return allXlsx ? "valid" : "invalid";
}

export function FileUploadDropzone({ onFiles }: { onFiles: (files: FileList) => void }) {
  const [drag, setDrag] = useState<DragState>("idle");
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div
      className={`files-dropzone ${drag === "valid" ? "dragging" : ""} ${drag === "invalid" ? "invalid" : ""}`}
      role="button"
      tabIndex={0}
      aria-label="Upload Excel files"
      onClick={() => inputRef.current?.click()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDrag(dragKind(event.dataTransfer));
      }}
      onDragLeave={() => setDrag("idle")}
      onDrop={(event) => {
        event.preventDefault();
        const kind = dragKind(event.dataTransfer);
        setDrag("idle");
        if (kind !== "invalid" && event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
      }}
    >
      <div className="dropzone-icons" aria-hidden="true">
        <Upload size={18} />
        <FileSpreadsheet size={18} />
      </div>
      {drag === "invalid" ? (
        <span className="dropzone-error">Only Excel .xlsx files are supported.</span>
      ) : (
        <>
          <strong>Upload Excel files (.xlsx)</strong>
          <span>Drag and drop or click to browse</span>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={UPLOAD_ACCEPT}
        multiple
        hidden
        aria-label="Upload Excel file"
        onChange={(event) => {
          if (event.target.files?.length) onFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </div>
  );
}
