import { Loader2, X } from "lucide-react";
import { formatBytes, type UploadedFile } from "../../types/files";

const STATUS_LABEL: Record<UploadedFile["status"], string> = {
  uploading: "Uploading",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed"
};

export function UploadedFileItem({ file, onRemove }: { file: UploadedFile; onRemove: () => void }) {
  const busy = file.status === "uploading" || file.status === "processing";
  return (
    <li className="file-item">
      <div className="file-main">
        <span className="file-name" title={file.filename}>
          {file.filename}
        </span>
        <span className="file-meta">
          <span className="file-size">{formatBytes(file.size_bytes)}</span>
          <span className={`file-status status-${file.status}`}>
            {busy ? <Loader2 size={12} className="spin" /> : null}
            {STATUS_LABEL[file.status]}
          </span>
        </span>
        {file.status === "failed" && file.error ? <span className="file-error">{file.error}</span> : null}
      </div>
      <button
        className="file-remove"
        aria-label={`Remove ${file.filename}`}
        onClick={() => {
          const inUse = file.status === "ready";
          if (!inUse || window.confirm(`Remove "${file.filename}"? It may be in use by the assistant.`)) {
            onRemove();
          }
        }}
      >
        <X size={15} />
      </button>
    </li>
  );
}
