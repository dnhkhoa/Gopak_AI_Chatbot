import { AlertCircle, ChevronDown, FileSpreadsheet, RotateCcw } from "lucide-react";
import { useRef, useState } from "react";
import type { UseFiles } from "../../hooks/useFiles";
import { formatBytes, UPLOAD_ACCEPT } from "../../types/files";
import { UploadedFileItem } from "./UploadedFileItem";

export function UploadedFilesPanel({ files }: { files: UseFiles }) {
  const [open, setOpen] = useState(true);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const totalBytes = files.files.reduce((sum, f) => sum + f.size_bytes, 0);

  return (
    <section className={`files-panel ${open ? "open" : "collapsed"}`} aria-label="Uploaded files">
      <button className="files-header" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span className="files-title">
          <FileSpreadsheet size={16} />
          Uploaded files
        </span>
        <span className="files-count">{files.files.length}</span>
        <ChevronDown size={16} className={`files-chevron ${open ? "up" : ""}`} />
      </button>

      {open ? (
        <div className="files-body">
          <div
            className={`files-dropzone ${dragging ? "dragging" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (event.dataTransfer.files.length) void files.upload(event.dataTransfer.files);
            }}
          >
            <strong>Upload Excel files (.xlsx)</strong>
            <span>Drag and drop or click to browse</span>
            <input
              ref={inputRef}
              type="file"
              accept={UPLOAD_ACCEPT}
              multiple
              hidden
              aria-label="Upload Excel file"
              onChange={(event) => {
                if (event.target.files?.length) void files.upload(event.target.files);
                event.target.value = "";
              }}
            />
          </div>

          {files.error ? (
            <div className="files-alert" role="alert">
              <AlertCircle size={14} />
              <span>{files.error}</span>
              <button className="files-retry" onClick={() => void files.retry()} aria-label="Retry upload">
                <RotateCcw size={13} /> Retry
              </button>
            </div>
          ) : null}

          {files.files.length ? (
            <ul className="files-list">
              {files.files.map((file) => (
                <UploadedFileItem key={file.id} file={file} onRemove={() => void files.remove(file.id)} />
              ))}
            </ul>
          ) : (
            <div className="files-empty">{files.loading ? "Loading files…" : "No files uploaded yet."}</div>
          )}

          {files.files.length ? (
            <div className="files-footer">
              <span>{files.files.length} file{files.files.length === 1 ? "" : "s"} uploaded</span>
              <span>{formatBytes(totalBytes)} total</span>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
